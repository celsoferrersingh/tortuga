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


# Folga da borda do quadro (~0,4% ≈ 3 px em 720).
#
# Por que existe: a area util quase sempre e desenhada ATE a borda da imagem, e
# quem esta perto da camera sai CORTADO na base do quadro — o "pe" dessa pessoa
# passa a ser exatamente a borda. Um ponto exatamente SOBRE a aresta do poligono
# e ambiguo no teste de pertencimento e caia para fora, de modo que a pessoa
# deixava de ser analisada sem nenhum aviso. Puxando a ancora alguns pixels para
# dentro do quadro, o caso deixa de ser ambiguo e passa a ser decidido pela
# geometria real da area, nao pelo arredondamento da borda.
BORDA = 0.004


def _ancora(bbox, usar_pe, largura=1.0, altura=1.0):
    """(x, y) normalizado que representa a posicao da deteccao."""
    x1, y1, x2, y2 = bbox[0], bbox[1], bbox[2], bbox[3]
    cx = (x1 + x2) / 2.0
    cy = y2 if usar_pe else (y1 + y2) / 2.0     # pe = base da caixa
    nx = cx / float(largura or 1)
    ny = cy / float(altura or 1)
    # nunca exatamente na borda do quadro
    nx = min(max(nx, BORDA), 1.0 - BORDA)
    ny = min(max(ny, BORDA), 1.0 - BORDA)
    return nx, ny


def dentro_da_area(bbox, poligonos, largura, altura, usar_pe=True):
    """True se a deteccao pertence a area util (ou se nao ha area definida)."""
    if not poligonos:
        return True
    if not bbox:
        return True
    nx, ny = _ancora(bbox, usar_pe, largura, altura)
    return any(ponto_no_poligono(nx, ny, p) for p in poligonos if p and len(p) >= 3)


def filtrar(deteccoes, poligonos, largura, altura, chave="bbox", usar_pe=True):
    """Devolve so as deteccoes dentro da area util."""
    if not poligonos:
        return deteccoes
    return [d for d in (deteccoes or [])
            if dentro_da_area(d.get(chave), poligonos, largura, altura, usar_pe)]


def _e_pessoa(d):
    return "person" in str(d.get("class_name", "")).lower()


def _pertence(epi_bbox, pessoa_bbox, margem=0.15):
    """O EPI esta sobre esta pessoa? (centro do EPI dentro da caixa dela)."""
    if not epi_bbox or not pessoa_bbox:
        return False
    px1, py1, px2, py2 = pessoa_bbox[:4]
    mw = (px2 - px1) * margem
    mh = (py2 - py1) * margem
    cx = (epi_bbox[0] + epi_bbox[2]) / 2.0
    cy = (epi_bbox[1] + epi_bbox[3]) / 2.0
    return (px1 - mw) <= cx <= (px2 + mw) and (py1 - mh) <= cy <= (py2 + mh)


def filtrar_cena(deteccoes, poligonos, largura, altura):
    """Filtra a cena inteira com o criterio correto para CADA tipo de deteccao.

    Por que nao basta testar a geometria de tudo: a area util e desenhada sobre
    o CHAO, mas o capacete fica na altura da CABECA. Numa camera alta e inclinada
    a cabeca de quem esta dentro da demarcacao aparece ACIMA do poligono na
    imagem — testar o capacete pela geometria o descartaria e o sistema acusaria
    "capacete ausente". Falso positivo de violacao, o pior erro possivel aqui.

    A regra certa: o EPI pertence a PESSOA, nao ao chao.
      1. pessoas  -> entram se o PE estiver dentro do poligono;
      2. EPIs     -> entram se estiverem sobre alguma pessoa que entrou;
      3. sem nenhuma pessoa detectada -> cai no criterio geometrico (cena sem
         gente, so objetos: vale o que estiver dentro).
    """
    if not poligonos:
        return deteccoes
    dets = list(deteccoes or [])
    pessoas = [d for d in dets if _e_pessoa(d)]
    objetos = [d for d in dets if not _e_pessoa(d)]

    if not pessoas:
        # ninguem em cena: decide objeto por objeto, pela geometria
        return [d for d in objetos
                if dentro_da_area(d.get("bbox"), poligonos, largura, altura, usar_pe=False)]

    dentro = [p for p in pessoas
              if dentro_da_area(p.get("bbox"), poligonos, largura, altura, usar_pe=True)]
    if not dentro:
        return []                      # so ha gente fora da area: nada a analisar

    mantidos = list(dentro)
    for o in objetos:
        if any(_pertence(o.get("bbox"), p.get("bbox")) for p in dentro):
            mantidos.append(o)
    return mantidos


def para_pixels(poligonos, largura, altura):
    """Converte poligonos normalizados em pixels, para desenhar sobre o frame."""
    out = []
    for p in poligonos or []:
        if p and len(p) >= 3:
            out.append([[int(x * largura), int(y * altura)] for x, y in p])
    return out
