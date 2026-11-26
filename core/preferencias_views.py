from io import BytesIO
from uuid import uuid4

from PIL import Image, ImageOps, UnidentifiedImageError
from django.core.files.base import ContentFile
from django.db import transaction
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from .models import Usuario
from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect

@login_required
@require_http_methods(["GET", "POST"])
def preferencias_view(request):
    usuario = request.user
    bases = {"GERENTE": "gerente", "VENDEDOR": "vendedor", "ADMINISTRATIVO": "administrativo"}
    perfil = bases.get(usuario.perfil)
    if not usuario.ativo or not usuario.is_active or not perfil:
        from django.contrib.auth import logout
        logout(request)
        return redirect("login")
    if request.method == "POST":
        acao = request.POST.get("acao")
        conteudo = None
        if acao == "enviar_foto":
            arquivo = request.FILES.get("foto")
            if not arquivo or arquivo.size > 5 * 1024 * 1024:
                return JsonResponse({"erro": "Escolha JPG ou PNG de até 5 MB."}, status=400)
            try:
                with Image.open(arquivo) as imagem:
                    if imagem.format not in {"JPEG", "PNG"} or imagem.width * imagem.height > 20_000_000:
                        raise ValueError("Formato ou dimensões inválidos")
                    imagem = ImageOps.exif_transpose(imagem).convert("RGB")
                    imagem.thumbnail((512, 512))
                    buffer = BytesIO()
                    imagem.save(buffer, format="JPEG", quality=88)
                    conteudo = ContentFile(buffer.getvalue())
            except (OSError, ValueError, UnidentifiedImageError, Image.DecompressionBombError):
                return JsonResponse({"erro": "Imagem inválida ou muito grande."}, status=400)
        elif acao != "remover_foto":
            return JsonResponse({"erro": "Ação inválida."}, status=400)
        with transaction.atomic():
            conta = Usuario.objects.select_for_update().get(pk=usuario.pk)
            anterior = conta.foto_perfil.name
            storage = conta.foto_perfil.storage
            if conteudo is not None:
                conta.foto_perfil.save(f"{conta.pk}/{uuid4().hex}.jpg", conteudo, save=False)
            else:
                conta.foto_perfil = ""
            conta.save(update_fields=["foto_perfil"])
            from .demo_storage import _scope
            scope = _scope.get()
            prefix = f"demos/{scope}/perfis/{conta.pk}/" if scope else f"perfis/{conta.pk}/"
            if anterior and anterior.startswith(prefix):
                transaction.on_commit(lambda: storage.delete(anterior), robust=True)
        return JsonResponse({"foto": conta.foto_perfil.url if conta.foto_perfil else ""})
    return render(request, "core/preferencias.html", {"base_painel": f"core/{perfil}_base.html"})
