from django.utils.functional import cached_property


class OrganizationMixin:
    @cached_property
    def active_members(self):
        return self.members


class OrganizationMemberMixin:
    def has_permission(self, user):
        if user.active_organization_id == self.organization_id:
            return True
        return False

    def has_admin_permission(self, user):
        """Check if user has admin-level access in this org member's organization."""
        if user.active_organization_id != self.organization_id:
            return False
        return getattr(self, 'is_admin', False)

    def has_manager_permission(self, user):
        """Check if user has manager-level access in this org member's organization."""
        if user.active_organization_id != self.organization_id:
            return False
        return getattr(self, 'is_manager', False)
