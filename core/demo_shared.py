from django.conf import settings
from django.contrib.auth.hashers import check_password
from django.contrib.auth import SESSION_KEY, BACKEND_SESSION_KEY, HASH_SESSION_KEY, logout
from django.core.exceptions import PermissionDenied
from django.db import connection, DatabaseError
from django.http import HttpResponseForbidden, HttpResponse, FileResponse, JsonResponse
from django.shortcuts import redirect, render
from django.middleware.csrf import rotate_token
from django.utils.cache import add_never_cache_headers
from django.views.decorators.csrf import csrf_protect
from .demo_storage import DemoStorage, demo_media_scope

class ReadOnlyStorage(DemoStorage):
    def save(self, *args, **kwargs):
        raise PermissionDenied('Demonstração somente para consulta.')
    def delete(self, *args, **kwargs):
        raise PermissionDenied('Demonstração somente para consulta.')

@csrf_protect
def choose_role(request):
    from .models import Usuario
    from .forms import LoginForm
    form = LoginForm(request.POST if request.method == 'POST' else None)
    if request.method == 'POST':
        if 'perfil' not in request.POST:
            if form.is_valid():
                role = form.cleaned_data['username']
                user = Usuario.objects.filter(username=role, perfil=role.upper(), ativo=True, is_superuser=False).first() if role in ('gerente', 'vendedor', 'administrativo') else None
                if user and check_password(form.cleaned_data['password'], user.password):
                    return enter_role(request, user)
                form.add_error(None, 'Usuário ou senha demonstrativa inválidos.')
            return render(request, 'core/login.html', {'form': form})
        role = request.POST.get('perfil', '')
        if role not in ('gerente', 'vendedor', 'administrativo'):
            return HttpResponseForbidden('Perfil inválido.')
        user = Usuario.objects.filter(username=role, perfil=role.upper(), ativo=True, is_superuser=False).first()
        if not user:
            return HttpResponseForbidden('Perfil indisponível.')
        return enter_role(request, user)
    role = request.GET.get('perfil', '')
    if role in ('gerente', 'vendedor', 'administrativo'):
        return render(request, 'core/demo_shared.html', {'selected_role': role})
    return render(request, 'core/login.html', {'form': form})

def enter_role(request, user):
    request.session.flush()
    request.session[SESSION_KEY] = str(user.pk)
    request.session[BACKEND_SESSION_KEY] = 'django.contrib.auth.backends.ModelBackend'
    request.session[HASH_SESSION_KEY] = user.get_session_auth_hash()
    rotate_token(request)
    return redirect('painel')

class ReadOnlyMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response
    def __call__(self, request):
        request.demo_shared = True
        path = request.path_info
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT current_schema(), current_schemas(false), current_setting('transaction_read_only')")
                if cursor.fetchone() != (settings.DEMO_SCHEMA, [settings.DEMO_SCHEMA], 'on'):
                    return HttpResponse('Ambiente de demonstração indisponível.', status=503)
                cursor.execute('SELECT 1 FROM demo_lifecycle WHERE id=1')
                if not cursor.fetchone():
                    return HttpResponse('Ambiente de demonstração indisponível.', status=503)
            with demo_media_scope(settings.DEMO_SCHEMA):
                if path.startswith('/media/') and settings.DEBUG and request.method in ('GET', 'HEAD'):
                    from django.core.files.storage import default_storage
                    try:
                        response = FileResponse(default_storage.open(path[len('/media/'):], 'rb'))
                    except (PermissionDenied, OSError):
                        response = HttpResponseForbidden()
                elif path.startswith(('/admin/', '/api/', '/media/')):
                    response = HttpResponseForbidden()
                elif path in ('/login/', '/accounts/login/', '/demo/entrar/'):
                    response = redirect('demo_perfil')
                elif path == '/accounts/logout/':
                    if request.method not in ('GET', 'HEAD', 'POST'):
                        return HttpResponseForbidden()
                    logout(request)
                    response = redirect('demo_perfil')
                elif request.method not in ('GET', 'HEAD') and not (path == '/demo/perfil/' and request.method == 'POST'):
                    response = JsonResponse({'erro': 'Alterações nos registros estão desativadas neste ambiente.'}, status=403)
                    response['X-RC-Demo-Blocked'] = '1'
                else:
                    response = self.get_response(request)
                add_never_cache_headers(response)
                return response
        except DatabaseError:
            return HttpResponse('Ambiente de demonstração indisponível.', status=503)
