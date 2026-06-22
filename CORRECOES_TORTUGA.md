# Tortuga — Diagnóstico e Correções (pré-banca Fase 2)

> Resumo do que estava quebrado, o que foi corrigido e como testar/retreinar antes da banca.

## 1. Por que parou de detectar

O re-treino de 29 mil imagens (para adicionar **bota** e **protetor auricular**) regrediu por problemas **no dataset**, não na arquitetura:

1. **Protetor auricular com 0 imagens.** A fonte baixada como `hearing-protection` continha, na verdade, *Boots/Helmet/Person/Vest* — nenhum protetor auricular. As classes `Ear Protection` / `NO-Ear Protection` ficaram com **0 instâncias** no treino.
2. **Contaminação por anotação parcial.** Misturar datasets que rotulam só parte dos EPIs ensina o modelo que óculos/botas não rotulados são "fundo" — degradando **todas** as classes, inclusive as que funcionavam.
3. **Desbalanceamento severo.** Hardhat 22.005 × Óculos 518 (≈42:1); negativos de bota 400.
4. **Gap de domínio + inferência a 320px.** Alto mAP no *val* (imagens de obra) mas falha em webcam de sala; e a GUI rodava a detecção a 320px, encolhendo EPIs pequenos abaixo do detectável.

## 2. O que foi corrigido

| Arquivo | Mudança |
|---|---|
| `server/models/` | Restaurados os modelos que funcionavam em maio: **`best.pt` = óculos**, **`best.old.pt` = capacete/colete/máscara** (modo DUAL). O modelo de 12 classes foi preservado em **`best_merged12.pt`**. |
| `server/gui.py` | Inferência de EPI de **320 → 640 px** (igual ao treino). Novo parâmetro `--det-size` (use 960 se sobrar FPS). |
| `server/app.py` | Dashboard agora lista os 5 EPIs obrigatórios (estava com 3 fixos). |
| `server/train_model.py` | **Relatório pré-voo** de distribuição de classes; **aborta** treino com classe vazia; salva em **staging** (`best_retrained.pt`) com validação obrigatória antes de promover — fim da regressão silenciosa. Novos comandos `--analyze` e `--force`. |
| `server/download_datasets.py` | **Verifica as classes** de cada dataset baixado e acusa fonte errada na hora (era o que faltava para pegar o protetor auricular). |
| Limpeza | Removidos `__pycache__`, `download_log.txt`, dataset vazio `safety-boots-ppe`; `hearing-protection` renomeado para `boots-helmet-vest` (nome reflete o conteúdo real). `.gitignore` atualizado. |

## 3. Teste rápido ANTES da banca (5 min)

```bash
cd server
python gui.py                 # webcam padrão, 640px, pose ligada
# Confirme: detecta capacete, colete, óculos (e máscara) em tempo real.
python gui.py --det-size 960  # se quiser mais alcance em EPIs pequenos
python diag.py                # lista detecções com limiar 5% (debug)
```

A Fase 2 (pose, RULA/REBA, queda, multi-pessoa) usa modelo COCO e **não** foi afetada pela regressão — deve funcionar normalmente.

## 4. Como re-treinar CERTO (adicionar bota + protetor auricular)

```bash
cd server
# 1) Baixe uma fonte REAL de protetor auricular (ex.: SH17, que tem ear protection + bota)
python download_datasets.py        # agora verifica as classes de cada fonte
# 2) Confira a distribuição ANTES de gastar horas de GPU:
python train_model.py --merge-only
python train_model.py --analyze    # aborta mentalmente se alguma classe = 0
# 3) Treine (a guarda impede classes vazias):
python train_model.py --epochs 100 --batch 16
# 4) Valide e teste ao vivo o modelo em staging:
python train_model.py --validate
python gui.py --model models/best_retrained.pt
# 5) Só se passar nas metas E detectar bem na sala: promova
#    copie best_retrained.pt -> best.pt   (detector entra em modo SINGLE 12 classes)
```

## 5. Pendências (exigências do descritivo ainda abertas)

- **Dataset próprio** rotulado na sala da FIAP — o item 4.6 **exige** dados do próprio grupo, não só públicos. Use-o também como validação "mundo real".
- **Material de pitch** (≤ 5 slides + vídeo de backup) para Fases 1 e 2.
- Medir e registrar as métricas marcadas como "A VALIDAR" na máquina da demo.

## 6. Entregáveis gerados (pasta `entregaveis/`)

- `Matriz_Conformidade_Tortuga.docx` — requisito a requisito × status × evidência.
- `Relatorio_Tecnico_Fase1_Tortuga.docx` — arquitetura, treino, métricas, erros, plano.
- `Relatorio_Tecnico_Fase2_Tortuga.docx` — pose, taxonomia, RULA/REBA, temporal, integração.
