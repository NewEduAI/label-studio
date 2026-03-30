"""Task assignment actions for the Data Manager."""

from core.permissions import AllPermissions
from data_manager.actions import DataManagerAction
from projects.models import ProjectMember
from users.models import User

all_permissions = AllPermissions()


def assign_annotators(project, queryset, **kwargs):
    request = kwargs.get('request')
    user_ids_str = request.data.get('user_ids', '') if request else ''

    if isinstance(user_ids_str, list):
        user_ids = [int(uid) for uid in user_ids_str if uid]
    else:
        user_ids = [int(uid.strip()) for uid in str(user_ids_str).split(',') if uid.strip()]

    if not user_ids:
        return {'processed_items': 0, 'detail': 'No annotators selected'}

    valid_member_user_ids = set(
        ProjectMember.objects.filter(
            project=project,
            enabled=True,
            role=ProjectMember.ProjectRoleChoices.ANNOTATOR,
            user_id__in=user_ids,
        ).values_list('user_id', flat=True)
    )

    if not valid_member_user_ids:
        return {'processed_items': 0, 'detail': 'Selected users are not project members'}

    users = User.objects.filter(id__in=valid_member_user_ids)
    count = 0
    for task in queryset:
        task.assignees.add(*users)
        count += 1

    return {
        'processed_items': count,
        'detail': f'Assigned {len(valid_member_user_ids)} annotator(s) to {count} task(s)',
    }


def assign_annotators_form(user, project):
    members = ProjectMember.objects.filter(
        project=project,
        enabled=True,
        role=ProjectMember.ProjectRoleChoices.ANNOTATOR,
    ).select_related('user')

    options = []
    for member in members:
        u = member.user
        name = u.first_name
        if u.last_name:
            name = f'{name} {u.last_name}'.strip()
        if not name:
            name = u.email or u.username
        options.append({'value': str(u.id), 'label': name})

    return [
        {
            'columnCount': 1,
            'fields': [
                {
                    'type': 'select',
                    'name': 'user_ids',
                    'label': 'Select Annotators',
                    'options': options,
                    'searchable': True,
                }
            ],
        }
    ]


def delete_annotator_assignments(project, queryset, **kwargs):
    count = 0
    for task in queryset:
        task.assignees.clear()
        count += 1

    return {
        'processed_items': count,
        'detail': f'Removed all annotator assignments from {count} task(s)',
    }


actions: list[DataManagerAction] = [
    {
        'entry_point': assign_annotators,
        'permission': all_permissions.tasks_change,
        'title': 'Assign Annotators',
        'order': 50,
        'dialog': {
            'text': 'Select annotators to assign to the selected tasks.',
            'type': 'confirm',
            'form': assign_annotators_form,
        },
    },
    {
        'entry_point': delete_annotator_assignments,
        'permission': all_permissions.tasks_change,
        'title': 'Delete Assignments',
        'order': 103,
        'dialog': {
            'text': 'You are going to remove all annotator assignments from the selected tasks. Please confirm.',
            'type': 'confirm',
        },
    },
]
