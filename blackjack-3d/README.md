# Blackjack 3D: série interativa "HIT or STAND?"

Série de Reels em 3D (Blender/Cycles) para público internacional (textos em inglês).
Cada **mão** vira 3 vídeos 1080×1920 / 30 fps, mais uma capa para cada um:

| Arquivo | O que é |
|---|---|
| `videos/handNN_1_episode.mp4` | Abre explicando o formato ("Interactive blackjack, you make the call"), câmera desce até a mesa enquanto as cartas são distribuídas, mostra os totais, pergunta **HIT or STAND?** e termina com **dois espaços lado a lado** (HIT / STAND) para você colocar os reels de decisão. A partir da mão 2, tem um espaço **"PREVIOUSLY"** no canto superior esquerdo para os reels anteriores. |
| `videos/handNN_2_hit.mp4` | Recapitula a mão para quem chega direto pelo feed ("You chose HIT · you had 16 vs dealer 10"), mostra o que acontece, o resultado e a lição de estratégia básica. Também tem o espaço "PREVIOUSLY". |
| `videos/handNN_3_stand.mp4` | Igual, para quem escolheu STAND. |
| `videos/*_cover.jpg` | Capa de cada Reel, sem spoiler do resultado. |
| `videos/GUIDE.md` | Ordem de postagem, **posição e tempo exatos de cada espaço** (para encaixar os reels no Edits) e legendas prontas. |

Os vídeos não têm áudio: coloque a música no Edits.

## Como a série funciona
- `hands.py` define as mãos. Cada mão tem uma ordem fixa no sapato, então os vídeos HIT e STAND são
  os dois "e se" honestos da mesma distribuição. O dealer para em todo 17, como está impresso na mesa.
- A lição no fim usa a estratégia básica (só hit/stand). Algumas mãos foram escolhidas para a jogada
  certa perder, o que gera discussão nos comentários.

## Gerar mais vídeos
```bash
python3 series.py --from 1 --to 20 --bpy-python /caminho/python-com-bpy   # CPU (lento)
bash render_vast.sh                                                         # GPU (vast.ai etc.)
```
Para criar mãos novas, acrescente entradas em `HANDS` no `hands.py` (`python3 hands.py` mostra o
resultado de cada ramo antes de renderizar).

## Como é renderizado
1. **Plates compartilhados** (uma vez só): a abertura com bokeh do cassino, o fundo da mesa vista de
   cima e os 60 quadros do movimento de grua, tudo sem cartas.
2. **Por mão**: só a área que as cartas e fichas tocam (com sombras, desfoque e motion blur) é
   renderizada de novo, e o `composite.py` cola essa área por cima dos plates, só onde algo mudou.
   Isso deixa cada mão uns 5× mais barata, sem emendas visíveis.
3. `make_videos.py` monta os quadros, faz o push-in suave, desenha os gráficos (`overlay/`) e codifica.

Arquivos: `blackjack3d.py` (cena e render), `make_cards.py` (texturas das cartas), `composite.py`,
`make_videos.py`, `overlay/overlay.html`, `series.py`, `render_vast.sh`.
