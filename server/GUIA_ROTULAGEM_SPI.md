# Guia de Rotulagem — Dataset Real da SPI

As 99 fotos da visita técnica são **close-ups dos EPIs da SPI**. Elas entram como
dados **adicionais** (o dataset do Roboflow continua sendo a base). Objetivo: o
modelo passar a reconhecer os equipamentos específicos da SPI e validar em "mundo real".

## 1. Mapeamento das classes (use os mesmos 12 rótulos do `merged`)

| Equipamento na foto            | Classe YOLO (id) |
|--------------------------------|------------------|
| Capacete branco                | `Hardhat` (0)          |
| Óculos de proteção (Volk/transp.) | `Safety Glasses` (4) |
| Respirador 3M / máscara facial | `Mask` (6)             |
| Protetor auricular (plug/abafador) | `Ear Protection` (8) |
| Colete refletivo (se aparecer) | `Safety Vest` (2)      |
| Bota de segurança (se aparecer)| `Safety Boots` (10)    |

As classes `NO-*` (ímpares) são para **ausência** e não se aplicam a fotos do
equipamento isolado. **Luvas não têm classe** nesta taxonomia de 12 — ignore-as
por enquanto (não rotule).

## 2. Passo a passo

1. **Pré-rótulo automático** (na máquina com GPU):
   ```
   python prelabel_spi.py
   ```
   Gera `.txt` candidatos em `datasets/spi_real/<train|valid>/labels/` e prévias
   anotadas em `.../preview/`. Como são close-ups, algumas saem imperfeitas — por isso revise.

2. **Revisão** — escolha uma ferramenta:
   - **Roboflow (recomendado):** crie um projeto *Object Detection*, faça upload das
     imagens de `spi_real`, importe os labels YOLO, **corrija as caixas e classes**,
     e exporte no formato *YOLOv8* de volta para `spi_real`.
   - **LabelImg (offline):** `pip install labelImg`, abra a pasta `images`, ative o
     formato **YOLO**, e edite. Salve os `.txt` na pasta `labels` correspondente.

3. **Regras de qualidade:**
   - A caixa cobre **o EPI**, não a mesa/fundo.
   - Apague caixas erradas; ajuste a classe quando o pré-rótulo errar.
   - Uma imagem pode ter mais de um EPI (rotule todos).

4. **Fine-tune** (na GPU), só depois da revisão:
   ```
   python finetune_spi.py
   ```

## 3. O que NÃO fazer
- Não rotular a mesa, mãos ou objetos que não são EPI.
- Não mexer no dataset `merged` (ele é a base e fica intocado).
- Não promover `best_spi.pt` para produção antes de ver o relatório de validação.
