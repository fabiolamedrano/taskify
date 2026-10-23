def build_donut(todo, doing, done):
    total = todo + doing + done
    if not total:
        return {'total': 0, 'done_pct': 0, 'doing_end': 0}
    done_pct = round(100 * done / total)
    doing_end = min(100, done_pct + round(100 * doing / total))
    return {'total': total, 'done_pct': done_pct, 'doing_end': doing_end}