"""
roi_filter.py — Area util (regiao de interesse) · Projeto Tortuga

Delimita O QUE O SISTEMA PODE ANALISAR. E o inverso da zona de exclusao:

    zona de EXCLUSAO  -> remove um pedaco da cena (ex.: braco robotico fixo)
    AREA UTIL (ROI)   -> mantem SOMENTE o que esta dentro do poligono

Motivacao concreta: na Arena do NEXT so pode ser analisado o que estiver dentro
da demarcacao do chao. A plateia fica fora do poligono e, por construcao, fora
da analise — nao vira deteccao, nao vira evento, nao entra no banco. Isso e ao
mesmo tempo um requisito do evento e uma garantia de privacidade demonstravel.

Regra de pertencimento: usa-se o PE da pessoa (centro da base da caixa), nao o
centro geometrico. Numa camera alta e inclinada, como as do palco, o centro da
caixa de alguem de pe pode cair fora da demarcacao enquanto os pes estao
claramente dentro — e e o pe que diz onde a pessoa esta pisando. Para objetos
soltos (um EPI detectado sem pessoa) o centro e usado, por nao haver "pe".

Sem area util definida, nada e filtrado: a cena inteira vale, preservando o
comportamento anterior.
"""
from __future__ import annotations


def ponto_no_poligono(x, y, poly):
    """Ray casting. poly = [[x,y], ...] em coordenadas normalizadas (0..1)."""
    n = len(poly)
    if n < 3:
        return True                      # poligono degenerado nao filtra nada
    dentro = False
    j = n - 1
    for i in range(n):
        xi, yi = poly[i][0], poly[i][1]
        xj, yj = poly[j][0], poly[j][1]
        intersecta = ((yi > y) != (yj > y)) and \
                     (x < (xj - xi) * (y - yi) / ((yj - yi) or 1e-12) + xi)
        if intersecta:
            dentro = not dentro
        j = i
    return dentro


def _ancora(bbox, usar_pe):
    """(x, y) normalizado que representa a posicao da deteccao."""
    x1, y1, x2, y2 = bbox[0], bbox[1], bbox[2], bbox[3]
    cx = (x1 + x2) / 2.0
    cy = y2 if usar_pe else (y1 + y2) / 2.0     # pe = base da caixa
    return cx, cy


def dentro_da_area(bbox, poligonos, largura, altura, usar_pe=True):
    """True se a deteccao pertence a area util (ou se nao ha area definida)."""
    if not poligonos:
        return True
    if not bbox:
        return True
    cx, cy = _ancora(bbox, usar_pe)
    nx = cx / float(largura or 1)
    ny = cy / float(altura or 1)
    return any(ponto_no_poligono(nx, ny, p) for p in poligonos if p and len(p) >= 3)


def filtrar(deteccoes, poligonos, largura, altura, chave="bbox", usar_pe=True):
    """Devolve so as deteccoes dentro da area util."""
    if not poligonos:
        return deteccoes
    return [d for d in (deteccoes or [])
            if dentro_da_area(d.get(chave), poligonos, largura, altura, usar_pe)]


def para_pixels(poligonos, largura, altura):
    """Converte poligonos normalizados em pixels, para desenhar sobre o frame."""
    out = []
    for p in poligonos or []:
        if p and len(p) >= 3:
            out.append([[int(x * largura), int(y * altura)] for x, y in p])
    return out
