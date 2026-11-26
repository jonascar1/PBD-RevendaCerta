from django.core import signing
from django.core.management import CommandError
from .demo_lifecycle import lifecycle_lock, provision, expiry
from django.core.exceptions import PermissionDenied
from django.db import connection, DatabaseError
from django.http import HttpResponse, HttpResponseForbidden, FileResponse, Http404
from django.shortcuts import redirect, render
from django.middleware.csrf import get_token
from django.views.decorators.csrf import csrf_protect
from django.views.decorators.http import require_POST
from django.utils import timezone
from django.utils.cache import add_never_cache_headers
from django.contrib.auth import login
from django.core.files.storage import default_storage

from .demo_http_probe import PATTERN, schema_scope
from .demo_storage import demo_media_scope
COOKIE='rc_demo_local_context'
SALT='rc.demo.local.entry.v1'

def current_demo(request):
    try:
        name = signing.loads(request.COOKIES.get(COOKIE, ''), salt=SALT, max_age=86400)
        if isinstance(name, str) and PATTERN.fullmatch(name) and expiry(name) > timezone.now():
            return name
    except (signing.BadSignature, ValueError, DatabaseError, TypeError):
        pass
    return None

@csrf_protect
def entry(request):
    old = current_demo(request)
    if request.method == 'POST':
        action = request.POST.get('acao')
        if action not in ('criar', 'reiniciar'):
            return HttpResponseForbidden('Ação inválida.')
        if action == 'reiniciar' and not old:
            return HttpResponseForbidden('Demonstração inexistente ou expirada.')
        try:
            name = old if old and action == 'criar' else provision(replace=old)
        except CommandError as exc:
            return HttpResponse(str(exc), status=409, content_type='text/plain')
        response = redirect('/demo/perfil/')
        response.set_cookie(COOKIE, signing.dumps(name, salt=SALT), max_age=86400, httponly=True, samesite='Lax', secure=request.is_secure())
        if name != old:
            response.delete_cookie('rc_demo_session')
        return response
    return render(request, 'core/demo_acesso.html', {'entrada': True, 'demo_ativa': bool(old)})

def expiry_current():
    with connection.cursor() as cursor:
        cursor.execute('SELECT expira_em FROM demo_lifecycle WHERE id=1')
        row=cursor.fetchone()
    return row[0] if row else None

def active():
    deadline = expiry_current()
    return bool(deadline and deadline > timezone.now())

@csrf_protect
def switch_role(request):
    from .models import Usuario
    if request.method=='POST':
        role=request.POST.get('perfil')
        if role not in ('gerente','vendedor','administrativo'): return HttpResponseForbidden()
        user=Usuario.objects.filter(username=role,perfil=role.upper(),ativo=True).first()
        if not user: return HttpResponseForbidden('Conta de teste indisponível.')
        login(request,user,backend='django.contrib.auth.backends.ModelBackend')
        return redirect('painel')
    return render(request, 'core/demo_acesso.html', {'entrada': False})


class DemoLocalMiddleware:
    def __init__(self,get_response): self.get_response=get_response
    def __call__(self,request):
        with lifecycle_lock():
            return self.handle(request)
    def handle(self,request):
        if request.path_info in ('/demo/entrar/', '/login/', '/accounts/login/'):
            if request.path_info != '/demo/entrar/':
                return redirect('/demo/entrar/')
            # CSRF decorator handles this entry independently of the downstream stack.
            response=entry(request)
            add_never_cache_headers(response)
            return response
        if request.path_info == '/' and not request.COOKIES.get(COOKIE):
            return redirect('/demo/entrar/')
        try:
            name=signing.loads(request.COOKIES.get(COOKIE,''),salt=SALT,max_age=86400)
            if not isinstance(name,str) or not PATTERN.fullmatch(name): raise ValueError()
            with schema_scope(name), demo_media_scope(name):
                if not active(): return HttpResponseForbidden('Demonstração expirada.')
                request.demo_expira_em = expiry_current()
                if request.path_info.startswith('/media/'):
                    if request.method not in ('GET','HEAD'): return HttpResponseForbidden()
                    try:
                        response=FileResponse(default_storage.open(request.path_info[len('/media/'):],'rb'))
                    except (PermissionDenied, FileNotFoundError, OSError): return HttpResponseForbidden()
                elif request.path_info.startswith(('/admin/','/api/')):
                    return HttpResponseForbidden()
                else:
                    response=self.get_response(request)
                add_never_cache_headers(response)
                return response
        except (signing.BadSignature,ValueError,DatabaseError):
            return HttpResponseForbidden('Contexto de demonstração inválido. Acesse /demo/entrar/.')
