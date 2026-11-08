# Blackjack 3D: "HIT or STAND?"

Cena 3D de cassino feita inteiramente por código no Blender: mesa, feltro impresso, cartas,
fichas, sapato, bandeja de fichas, fundo de cassino com bokeh, luzes e movimentos de câmera.
Não há mão de dealer: as cartas saem do sapato, deslizam e viram sozinhas.

Saída em 1080×1920, 30 fps, pronta para o Edits:

| Clipe | Duração | O que acontece |
|---|---|---|
| `question.mp4` | 9 s | Abre no nível das fichas com bokeh; as 4 cartas são distribuídas enquanto a câmera sobe; fica parada a partir de ~3 s (espaço para o texto e a enquete) |
| `stand.mp4` | 5,5 s | O dealer vira a carta escondida (7 → 17); o jogador perde e as fichas são recolhidas |
| `hit.mp4` | 7 s | O jogador recebe um 5 (21); o dealer vira 17; o jogador recebe o pagamento em fichas |

## Renderizar na GPU (vast.ai)

1. Alugue uma máquina com GPU NVIDIA (RTX 3090/4090 é ótimo) e uma imagem Ubuntu (a de PyTorch serve).
2. Envie esta pasta para a máquina (upload do `blackjack-3d.zip` pelo Jupyter, ou `scp -P <porta> blackjack-3d.zip root@<ip>:~`).
3. Rode:

   ```bash
   unzip blackjack-3d.zip && cd blackjack-3d
   bash render_vast.sh --clip question --res 50 --samples 48   # teste rápido (~minutos)
   bash render_vast.sh                                          # versão final, os 3 clipes
   ```

   O script instala o que faltar (ffmpeg e libs), baixa o Blender e renderiza com OptiX.
   Se a máquina cair no meio, rode de novo: os quadros já prontos são pulados.

4. Baixe `render/question.mp4`, `render/stand.mp4` e `render/hit.mp4`.

Opções úteis (vão depois de `render_vast.sh`):

- `--clip question|stand|hit|all`
- `--samples 160`: qualidade (menos = mais rápido; o denoiser segura bem a partir de ~64)
- `--res 50`: resolução em %, para testes
- `--frames 0,84,269`: só alguns quadros (sai `render/<clip>/still_####.png`)
- `--save-blend`: salva o `.blend` para abrir e mexer no Blender

## Fazer a mão #2, #3…

Edite o bloco no topo do `blackjack3d.py`:

```python
PLAYER_CARDS = ["10S", "6H"]   # cartas do jogador
DEALER_UP = "10C"              # carta aberta do dealer
DEALER_HOLE = "7S"             # carta escondida (revelada nos clipes de resposta)
HIT_CARD = "5D"                # carta que o jogador recebe no clipe do HIT
PLAYER_WINS_ON_STAND = False   # resultado do clipe "stand"
PLAYER_WINS_ON_HIT = True      # resultado do clipe "hit"
```

Código = valor + naipe: `A 2 … 10 J Q K` + `S` (espadas), `H` (copas), `D` (ouros), `C` (paus).
As texturas estão em `textures/` (geradas pelo `make_cards.py`).

## Textos no Edits

| Clipe | Quando | Texto sugerido |
|---|---|---|
| question | 0–2,5 s | `HAND #1` |
| question | a partir de ~3 s | `HIT or STAND?` no topo + enquete entre as cartas do dealer e as suas |
| stand | ~1,5 s | `Dealer has 17` → `16 loses 😬` |
| hit | ~1,3 s | `21!` |
| hit | ~2,7 s | `Dealer 17 → YOU WIN` |

Deixe o terço de baixo livre: a legenda e os botões do Reels ficam ali.
