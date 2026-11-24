from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect

@login_required
def preferencias_view(request):
    usuario = request.user
    bases = {"GERENTE": "gerente", "VENDEDOR": "vendedor", "ADMINISTRATIVO": "administrativo"}
    perfil = bases.get(usuario.perfil)
    if not usuario.ativo or not usuario.is_active or not perfil:
        from django.contrib.auth import logout
        logout(request)
        return redirect("login")
    return render(request, "core/preferencias.html", {"base_painel": f"core/{perfil}_base.html"})
