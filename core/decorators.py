"""Decorators de controle de acesso por perfil de usuário."""

from functools import wraps

from django.contrib.auth import logout
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.shortcuts import redirect


def perfil_requerido(*perfis_permitidos):
    """
    Restringe o acesso à view aos perfis informados.

    Exige usuário autenticado e ativo, encerrando a sessão caso o cadastro
    tenha sido desativado e lançando PermissionDenied se o perfil não for
    autorizado.

    Exemplo de uso:
        @perfil_requerido("GERENTE")
        @perfil_requerido("GERENTE", "ADMINISTRATIVO")
    """

    def decorator(view_func):
        @wraps(view_func)
        @login_required
        def wrapper(request, *args, **kwargs):
            usuario = request.user

            # Encerra a sessão caso o usuário tenha sido desativado após o login.
            if not usuario.ativo:
                logout(request)
                return redirect("login")

            if usuario.perfil not in perfis_permitidos:
                raise PermissionDenied("Seu perfil não tem acesso a esta rota.")

            return view_func(request, *args, **kwargs)

        return wrapper

    return decorator