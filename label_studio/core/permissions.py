"""This file and its contents are licensed under the Apache License 2.0. Please see the included NOTICE for copyright information and LICENSE for a copy of the license."""

import logging  # noqa: I001
from typing import Optional

from pydantic import BaseModel, ConfigDict

import rules

logger = logging.getLogger(__name__)


class AllPermissions(BaseModel):
    model_config = ConfigDict(protected_namespaces=('__.*__', '_.*'))

    organizations_create: str = 'organizations.create'
    organizations_view: str = 'organizations.view'
    organizations_change: str = 'organizations.change'
    organizations_delete: str = 'organizations.delete'
    organizations_invite: str = 'organizations.invite'
    projects_create: str = 'projects.create'
    projects_view: str = 'projects.view'
    projects_change: str = 'projects.change'
    projects_delete: str = 'projects.delete'
    projects_reset_cache: str = 'projects.reset_cache'
    tasks_create: str = 'tasks.create'
    tasks_view: str = 'tasks.view'
    tasks_change: str = 'tasks.change'
    tasks_delete: str = 'tasks.delete'
    views_reset: str = 'views.reset'
    annotations_create: str = 'annotations.create'
    annotations_view: str = 'annotations.view'
    annotations_change: str = 'annotations.change'
    annotations_delete: str = 'annotations.delete'
    actions_perform: str = 'actions.perform'
    predictions_any: str = 'predictions.any'
    avatar_any: str = 'avatar.any'
    labels_create: str = 'labels.create'
    labels_view: str = 'labels.view'
    labels_change: str = 'labels.change'
    labels_delete: str = 'labels.delete'
    models_create: str = 'models.create'
    models_view: str = 'models.view'
    models_change: str = 'models.change'
    models_delete: str = 'models.delete'
    model_provider_connection_create: str = 'model_provider_connection.create'
    model_provider_connection_view: str = 'model_provider_connection.view'
    model_provider_connection_change: str = 'model_provider_connection.change'
    model_provider_connection_delete: str = 'model_provider_connection.delete'
    webhooks_view: str = 'webhooks.view'
    webhooks_change: str = 'webhooks.change'
    users_token_any: str = 'users.token.any'

    storages_view: str = 'storages.view'
    storages_change: str = 'storages.change'
    storages_sync: str = 'storages.sync'

    views_view: str = 'views.view'
    views_create: str = 'views.create'
    views_change: str = 'views.change'
    views_delete: str = 'views.delete'


all_permissions = AllPermissions()


class ViewClassPermission(BaseModel):
    GET: Optional[str] = None
    PATCH: Optional[str] = None
    PUT: Optional[str] = None
    DELETE: Optional[str] = None
    POST: Optional[str] = None


def make_perm(name, pred, overwrite=False):
    if rules.perm_exists(name):
        if overwrite:
            rules.remove_perm(name)
        else:
            return
    rules.add_perm(name, pred)


def _is_org_admin(user):
    """Check if user is admin+ in their active organization."""
    if not user.is_authenticated:
        return False
    from organizations.models import OrganizationMember

    try:
        om = OrganizationMember.objects.get(
            user=user, organization_id=user.active_organization_id, deleted_at__isnull=True,
        )
        return om.is_admin
    except OrganizationMember.DoesNotExist:
        return False


def _is_org_manager(user):
    """Check if user is manager+ in their active organization."""
    if not user.is_authenticated:
        return False
    from organizations.models import OrganizationMember

    try:
        om = OrganizationMember.objects.get(
            user=user, organization_id=user.active_organization_id, deleted_at__isnull=True,
        )
        return om.is_manager
    except OrganizationMember.DoesNotExist:
        return False


is_org_admin = rules.predicate(_is_org_admin)
is_org_manager = rules.predicate(_is_org_manager)

_admin_only_perms = {
    'organizations.change', 'organizations.delete', 'organizations.invite',
    'projects.delete', 'projects.reset_cache',
    'views.reset',
}

_manager_perms = {
    'projects.create', 'projects.change',
    'tasks.create', 'tasks.change', 'tasks.delete',
    'storages.change', 'storages.sync',
    'views.create', 'views.change', 'views.delete',
    'models.create', 'models.change', 'models.delete',
    'model_provider_connection.create', 'model_provider_connection.change',
    'model_provider_connection.delete',
    'webhooks.change',
    'labels.create', 'labels.change', 'labels.delete',
    'predictions.any',
}

for _, permission_name in all_permissions:
    if permission_name in _admin_only_perms:
        make_perm(permission_name, is_org_admin)
    elif permission_name in _manager_perms:
        make_perm(permission_name, is_org_manager)
    else:
        make_perm(permission_name, rules.is_authenticated)
