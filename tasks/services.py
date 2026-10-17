from notifications.models import Notification

def notify_assignment(task, actor):
    user = task.assigned_user
    if user and user != actor:
        Notification.objects.create(
            user=user,
            task=task,
            type=Notification.Type.ASSIGNMENT,
            message=f'Se te asigno "{task.title}"'[:255],
        )