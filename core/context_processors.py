def navigation(request):
    match = request.resolver_match
    if not match:
        return {}

    app, name = match.app_name, match.url_name
    if name == 'dashboard':
        section = 'dashboard'
    elif name == 'mine':
        section = 'mine'
    elif name in ('my_time', 'my_time_add', 'my_time_delete'):
        section = 'my_time'
    elif app in ('projects', 'tasks'):
        section = 'projects'
    else:
        section = app
    return {'nav_section': section}