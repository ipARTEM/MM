# D:\MM\mm08\views.py
from django.shortcuts import render

def index(request):
    return render(request, 'mm08/index.html', {'title': 'MM08 — старт'})
