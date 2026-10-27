def plain(number):
    return format(number.normalize(), 'f')


def plural(count, word):
    return f'{count} {word}{"" if count == 1 else "s"}'