from difflib import SequenceMatcher

from reference.models import Nuclides


def similarity(a, b):

    return SequenceMatcher(
        None,
        a.lower(),
        b.lower()
    ).ratio()


def match_nuclide(name):

    best = None

    score = 0

    for n in Nuclides.objects.all():

        s = similarity(
            name,
            str(n)
        )

        if s > score:

            score = s

            best = n

    return best, score