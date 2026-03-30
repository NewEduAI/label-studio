from organizations.models import OrganizationMember


class UserMixin:
    @property
    def is_annotator(self):
        """Check if user is an annotator in their active organization."""
        try:
            om = OrganizationMember.objects.get(
                user=self, organization_id=self.active_organization_id, deleted_at__isnull=True,
            )
            return om.role == OrganizationMember.RoleChoices.ANNOTATOR
        except OrganizationMember.DoesNotExist:
            return True

    def is_project_annotator(self, project):
        """Check if user has the annotator role in a specific project."""
        from projects.models import ProjectMember

        try:
            pm = ProjectMember.objects.get(user=self, project=project, enabled=True)
            return pm.role == ProjectMember.ProjectRoleChoices.ANNOTATOR
        except ProjectMember.DoesNotExist:
            return self.is_annotator

    def has_permission(self, user):
        return OrganizationMember.objects.filter(
            user=user, organization=user.active_organization, deleted_at__isnull=True
        ).exists()
