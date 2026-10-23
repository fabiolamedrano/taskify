class QueryStringMixin:
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        params = self.request.GET.copy()
        params.pop('page', None)
        context['query_string'] = params.urlencode()
        return context

def filter_options(request, param, choices, current, all_label='Todos', counts=None, fragment=''):
    suffix = f'#{fragment}' if fragment else ''
    options = []
    for value, label in [('', all_label), *choices]:
        params = request.GET.copy()
        params.pop('page', None)
        if value:
            params[param] = value
        else:
            params.pop(param, None)
        query = params.urlencode()
        option = {
            'label': label,
            'url': f'?{query}{suffix}' if query else f'{request.path}{suffix}',
            'active': current == value,
        }
        if counts is not None:
            option['count'] = counts.get(value, 0) if value else sum(counts.values())
        options.append(option)
    return options