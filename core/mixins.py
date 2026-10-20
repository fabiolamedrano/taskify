class QueryStringMixin:
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        params = self.request.GET.copy()
        params.pop('page', None)
        context['query_string'] = params.urlencode()
        return context

def filter_options(request, param, choices, current, all_label='Todos'):
    options = []
    for value, label in [('', all_label), *choices]:
        params = request.GET.copy()
        params.pop('page', None)
        if value:
            params[param] = value
        else:
            params.pop(param, None)
        query = params.urlencode()
        options.append({
            'label': label,
            'url': f'?{query}' if query else request.path,
            'active': current == value,
        })
    return options