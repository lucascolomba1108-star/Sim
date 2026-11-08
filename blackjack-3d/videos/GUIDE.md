# Interactive Blackjack: guia de postagem

Cada mão tem 3 Reels (1080x1920, 30 fps, com efeitos sonoros de cartas e fichas; coloque a música por cima no Edits) e uma capa para cada um (`*_cover.jpg`). Textos e legendas em inglês, para o público internacional.

## Primeiro post
`00_series_trailer.mp4`: explica como a série funciona. Poste antes de tudo e fixe no perfil.

## Regra das caixinhas
Uma caixinha só pode mostrar um reel que **já foi postado**. Por isso as caixinhas ficam só no **episódio**, que é o último a ser postado de cada mão. Os vídeos HIT e STAND **não têm caixinha**: no fim, eles mostram onde está a mão completa no perfil (a mesma fileira do grid).

## Ordem para postar cada mão
1. **STAND** (`handNN_3_stand.mp4`): sem caixinhas, só capa e legenda.
2. **HIT** (`handNN_2_hit.mp4`): sem caixinhas, só capa e legenda.
3. **Episódio** (`handNN_1_episode.mp4`), por último. Agora HIT e STAND já existem, então você coloca nas caixinhas:
   - tela final, moldura verde (esquerda) → o reel **HIT** que você acabou de postar; moldura vermelha (direita) → o reel **STAND**. De 12.5s até o fim (19.0s).
   - da mão 2 em diante, canto **PREVIOUSLY** (superior esquerdo) → o **episódio da mão anterior**, de 0.2s a 7.6s.

Postando nessa ordem, cada mão vira uma fileira no perfil: **episódio | HIT | STAND**, exatamente o que a tela final dos vídeos HIT/STAND mostra. Poste sempre os 3 de cada mão, sem outro post no meio, para as fileiras não desalinharem.

## Posição das caixinhas no episódio (pixels no quadro 1080x1920)
- PREVIOUSLY: x 36-216, y 262-582 (180x320, 9:16).
- HIT: x 130-510, y 560-1236 (380x676). STAND: x 570-950, y 560-1236 (380x676).
- Enquete (opcional): durante "HIT or STAND?" (7.6s-12.0s) o meio da mesa (y ~760-1000) fica livre.

## Mãos

### Mão 1: 16 contra 10 do dealer (estratégia básica: HIT)
- Cartas: você 10S 6H | dealer 10C + escondida 7S
- `hand01_1_episode.mp4` (19.0s)
- `hand01_2_hit.mp4` (18.9s): HIT → você 21, dealer 17: **GANHA**.
- `hand01_3_stand.mp4` (17.7s): STAND → você 16, dealer 17: **PERDE**.
- Legendas (copie e cole):
  - Episódio: `Hand #1: 16 vs dealer 10. HIT or STAND? Comment your move, then watch your reel 👇 #blackjack #cardgames #casino #interactive`
  - HIT: `Hand #1: you chose HIT. Did it pay off? 🃏 #blackjack #cardgames #casino`
  - STAND: `Hand #1: you chose STAND. Did it pay off? 🃏 #blackjack #cardgames #casino`

### Mão 2: soft 18 contra 9 do dealer (estratégia básica: HIT)
- Cartas: você AS 7D | dealer 9H + escondida KC
- `hand02_1_episode.mp4` (19.0s)
- `hand02_2_hit.mp4` (18.9s): HIT → você 21, dealer 19: **GANHA**.
- `hand02_3_stand.mp4` (17.7s): STAND → você SOFT 18, dealer 19: **PERDE**.
- Legendas (copie e cole):
  - Episódio: `Hand #2: soft 18 vs dealer 9. HIT or STAND? Comment your move, then watch your reel 👇 #blackjack #cardgames #casino #interactive`
  - HIT: `Hand #2: you chose HIT. Did it pay off? 🃏 #blackjack #cardgames #casino`
  - STAND: `Hand #2: you chose STAND. Did it pay off? 🃏 #blackjack #cardgames #casino`

### Mão 3: 12 contra 4 do dealer (estratégia básica: STAND)
- Cartas: você 9C 3D | dealer 4S + escondida 10H
- `hand03_1_episode.mp4` (19.0s)
- `hand03_2_hit.mp4` (18.9s): HIT → você BUST, dealer 14: **ESTOURA (BUST)**.
- `hand03_3_stand.mp4` (18.8s): STAND → você 12, dealer BUST: **GANHA**.
- Legendas (copie e cole):
  - Episódio: `Hand #3: 12 vs dealer 4. HIT or STAND? Comment your move, then watch your reel 👇 #blackjack #cardgames #casino #interactive`
  - HIT: `Hand #3: you chose HIT. Did it pay off? 🃏 #blackjack #cardgames #casino`
  - STAND: `Hand #3: you chose STAND. Did it pay off? 🃏 #blackjack #cardgames #casino`

### Mão 4: 15 contra 7 do dealer (estratégia básica: HIT)
- Cartas: você 8H 7C | dealer 7D + escondida JS
- `hand04_1_episode.mp4` (19.0s)
- `hand04_2_hit.mp4` (18.9s): HIT → você 19, dealer 17: **GANHA**.
- `hand04_3_stand.mp4` (17.7s): STAND → você 15, dealer 17: **PERDE**.
- Legendas (copie e cole):
  - Episódio: `Hand #4: 15 vs dealer 7. HIT or STAND? Comment your move, then watch your reel 👇 #blackjack #cardgames #casino #interactive`
  - HIT: `Hand #4: you chose HIT. Did it pay off? 🃏 #blackjack #cardgames #casino`
  - STAND: `Hand #4: you chose STAND. Did it pay off? 🃏 #blackjack #cardgames #casino`

### Mão 5: 13 contra 6 do dealer (estratégia básica: STAND)
- Cartas: você 10D 3C | dealer 6C + escondida QH
- `hand05_1_episode.mp4` (19.0s)
- `hand05_2_hit.mp4` (18.9s): HIT → você BUST, dealer 16: **ESTOURA (BUST)**.
- `hand05_3_stand.mp4` (18.8s): STAND → você 13, dealer BUST: **GANHA**.
- Legendas (copie e cole):
  - Episódio: `Hand #5: 13 vs dealer 6. HIT or STAND? Comment your move, then watch your reel 👇 #blackjack #cardgames #casino #interactive`
  - HIT: `Hand #5: you chose HIT. Did it pay off? 🃏 #blackjack #cardgames #casino`
  - STAND: `Hand #5: you chose STAND. Did it pay off? 🃏 #blackjack #cardgames #casino`

### Mão 6: 12 contra 2 do dealer (estratégia básica: HIT)
- Cartas: você 10H 2S | dealer 2D + escondida 9S
- `hand06_1_episode.mp4` (19.0s)
- `hand06_2_hit.mp4` (20.0s): HIT → você 21, dealer 19: **GANHA**.
- `hand06_3_stand.mp4` (18.8s): STAND → você 12, dealer 20: **PERDE**.
- Legendas (copie e cole):
  - Episódio: `Hand #6: 12 vs dealer 2. HIT or STAND? Comment your move, then watch your reel 👇 #blackjack #cardgames #casino #interactive`
  - HIT: `Hand #6: you chose HIT. Did it pay off? 🃏 #blackjack #cardgames #casino`
  - STAND: `Hand #6: you chose STAND. Did it pay off? 🃏 #blackjack #cardgames #casino`
