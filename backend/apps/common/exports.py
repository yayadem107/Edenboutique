"""Export des rapports en CSV (ouvrable dans Excel) via le paramètre `?export=csv`."""

import csv

from django.http import HttpResponse
from django.utils import timezone


def wants_csv(request):
    return request.query_params.get("export") == "csv"


def csv_response(filename, columns, rows):
    """
    columns : liste de tuples (clé, libellé de colonne)
    rows    : itérable de dictionnaires
    """
    response = HttpResponse(content_type="text/csv; charset=utf-8")
    stamp = timezone.localtime().strftime("%Y%m%d-%H%M")
    response["Content-Disposition"] = f'attachment; filename="{filename}-{stamp}.csv"'
    # BOM UTF-8 pour qu'Excel affiche correctement les accents.
    response.write("﻿")
    writer = csv.writer(response, delimiter=";")
    writer.writerow([label for _, label in columns])
    for row in rows:
        writer.writerow([row.get(key, "") for key, _ in columns])
    return response
