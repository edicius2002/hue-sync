# Coordinacion medida de pared y techo

## Metodo

Se reprodujeron `summer.wav` y `billie.wav` por `AnalysisEngine` con
`feed(bloque, offset, wall_t=t)` y se construyo cada `RenderContext` con
`cli.sync._context()`. El render se muestreo a 50 fps y con compensacion de
50 ms. Cada celda `S/B` de las tablas significa `summer/billie`.

Brillo es `max(R, G, B)`. `D` es distancia RGB euclidea media/mediana,
`<.02` el porcentaje de frames practicamente iguales, `r` la correlacion de
brillo, `F` el porcentaje de frames donde ambos canales saltan mas de 0.10,
y `T/P` el brillo medio techo/pared. `--` significa brillo constante y por
tanto correlacion indefinida.

Clasificacion: **redundante** si ambos WAV tienen `D < .02` en al menos 95%
de los frames; **conflictivo** si el destello simultaneo llega a 5%;
**consistente** en los demas casos. El 5% separa pulsos compartidos repetidos
de coincidencias aisladas: por ejemplo, 1.8% son 22 frames en 25 s.

## Matriz completa de pares ordenados

### Pared: combo

| Techo | Clase | D media/mediana S/B | <.02 S/B | r S/B | F S/B | T/P S/B |
|---|---|---|---|---|---|---|
| combo | redundante | 0.000/0.000, 0.000/0.000 | 100.0%/100.0% | 1.000/1.000 | 13.2%/13.0% | 1.00/1.00 |
| harmony | consistente | 0.451/0.498, 0.510/0.554 | 0.6%/0.2% | 0.116/0.398 | 0.3%/1.8% | 2.21/2.52 |
| bars | conflictivo | 0.036/0.183, 0.000/0.160 | 83.2%/20.0% | 0.920/0.896 | 13.1%/12.0% | 1.10/1.48 |
| beat_flash | conflictivo | 0.226/0.198, 0.169/0.162 | 0.2%/0.2% | 0.976/0.970 | 12.9%/11.8% | 1.67/1.63 |
| spectrum | consistente | 0.405/0.256, 0.448/0.246 | 1.1%/1.4% | -0.082/0.186 | 0.6%/1.3% | 2.03/1.52 |
| sustain | conflictivo | 0.143/0.070, 0.096/0.039 | 21.3%/36.9% | 0.602/0.905 | 6.7%/9.3% | 1.13/0.81 |
| idle | consistente | 0.312/0.264, 0.234/0.204 | 0.0%/0.0% | --/-- | 0.0%/0.0% | 0.28/0.31 |

### Pared: harmony

| Techo | Clase | D media/mediana S/B | <.02 S/B | r S/B | F S/B | T/P S/B |
|---|---|---|---|---|---|---|
| combo | consistente | 0.451/0.498, 0.510/0.554 | 0.6%/0.2% | 0.116/0.398 | 0.3%/1.8% | 0.45/0.40 |
| harmony | redundante | 0.000/0.000, 0.000/0.000 | 100.0%/100.0% | 1.000/1.000 | 0.3%/3.0% | 1.00/1.00 |
| bars | consistente | 0.460/0.564, 0.514/0.596 | 0.6%/0.2% | 0.050/0.272 | 0.3%/1.0% | 0.50/0.59 |
| beat_flash | consistente | 0.495/0.509, 0.506/0.546 | 0.0%/0.0% | 0.004/0.243 | 0.2%/0.7% | 0.76/0.65 |
| spectrum | consistente | 0.065/0.327, 0.048/0.370 | 22.5%/2.6% | 0.413/0.438 | 0.2%/2.0% | 0.92/0.60 |
| sustain | consistente | 0.397/0.561, 0.416/0.623 | 3.4%/0.4% | 0.042/0.382 | 0.3%/1.2% | 0.51/0.32 |
| idle | consistente | 0.743/0.752, 0.739/0.740 | 0.0%/0.0% | --/-- | 0.0%/0.0% | 0.13/0.12 |

### Pared: bars

| Techo | Clase | D media/mediana S/B | <.02 S/B | r S/B | F S/B | T/P S/B |
|---|---|---|---|---|---|---|
| combo | conflictivo | 0.036/0.183, 0.000/0.160 | 83.2%/20.0% | 0.920/0.896 | 13.1%/12.0% | 0.91/0.68 |
| harmony | consistente | 0.460/0.564, 0.514/0.596 | 0.6%/0.2% | 0.050/0.272 | 0.3%/1.0% | 2.01/1.70 |
| bars | redundante | 0.000/0.000, 0.000/0.000 | 100.0%/100.0% | 1.000/1.000 | 14.2%/14.6% | 1.00/1.00 |
| beat_flash | conflictivo | 0.235/0.224, 0.176/0.190 | 0.2%/0.2% | 0.909/0.923 | 14.0%/14.2% | 1.52/1.11 |
| spectrum | consistente | 0.415/0.343, 0.456/0.317 | 1.0%/0.4% | -0.094/0.111 | 0.6%/1.0% | 1.85/1.03 |
| sustain | conflictivo | 0.166/0.223, 0.119/0.187 | 17.7%/3.9% | 0.594/0.889 | 6.7%/8.5% | 1.03/0.55 |
| idle | consistente | 0.328/0.330, 0.256/0.258 | 0.0%/0.0% | --/-- | 0.0%/0.0% | 0.25/0.21 |

### Pared: beat_flash

| Techo | Clase | D media/mediana S/B | <.02 S/B | r S/B | F S/B | T/P S/B |
|---|---|---|---|---|---|---|
| combo | conflictivo | 0.226/0.198, 0.169/0.162 | 0.2%/0.2% | 0.976/0.970 | 12.9%/11.8% | 0.60/0.61 |
| harmony | consistente | 0.495/0.509, 0.506/0.546 | 0.0%/0.0% | 0.004/0.243 | 0.2%/0.7% | 0.76/0.65 |
| bars | conflictivo | 0.235/0.224, 0.176/0.190 | 0.2%/0.2% | 0.909/0.923 | 14.0%/14.2% | 0.66/0.90 |
| beat_flash | redundante | 0.000/0.000, 0.000/0.000 | 100.0%/100.0% | 1.000/1.000 | 22.2%/16.2% | 1.00/1.00 |
| spectrum | consistente | 0.459/0.325, 0.462/0.286 | 0.0%/0.0% | -0.142/0.116 | 1.0%/0.8% | 1.22/0.93 |
| sustain | conflictivo | 0.292/0.241, 0.256/0.209 | 0.2%/0.2% | 0.644/0.936 | 6.6%/8.3% | 0.68/0.50 |
| idle | consistente | 0.422/0.360, 0.321/0.274 | 0.0%/0.0% | --/-- | 0.0%/0.0% | 0.17/0.19 |

### Pared: spectrum

| Techo | Clase | D media/mediana S/B | <.02 S/B | r S/B | F S/B | T/P S/B |
|---|---|---|---|---|---|---|
| combo | consistente | 0.405/0.256, 0.448/0.246 | 1.1%/1.4% | -0.082/0.186 | 0.6%/1.3% | 0.49/0.66 |
| harmony | consistente | 0.065/0.327, 0.048/0.370 | 22.5%/2.6% | 0.413/0.438 | 0.2%/2.0% | 1.09/1.66 |
| bars | consistente | 0.415/0.343, 0.456/0.317 | 1.0%/0.4% | -0.094/0.111 | 0.6%/1.0% | 0.54/0.97 |
| beat_flash | consistente | 0.459/0.325, 0.462/0.286 | 0.0%/0.0% | -0.142/0.116 | 1.0%/0.8% | 0.82/1.08 |
| spectrum | redundante | 0.000/0.000, 0.000/0.000 | 100.0%/100.0% | 1.000/1.000 | 2.2%/5.8% | 1.00/1.00 |
| sustain | consistente | 0.349/0.293, 0.364/0.282 | 3.0%/1.4% | -0.059/0.184 | 0.2%/0.6% | 0.56/0.53 |
| idle | consistente | 0.678/0.426, 0.691/0.373 | 0.0%/0.0% | --/-- | 0.0%/0.0% | 0.14/0.20 |

### Pared: sustain

| Techo | Clase | D media/mediana S/B | <.02 S/B | r S/B | F S/B | T/P S/B |
|---|---|---|---|---|---|---|
| combo | conflictivo | 0.143/0.070, 0.096/0.039 | 21.3%/36.9% | 0.602/0.905 | 6.7%/9.3% | 0.89/1.23 |
| harmony | consistente | 0.397/0.561, 0.416/0.623 | 3.4%/0.4% | 0.042/0.382 | 0.3%/1.2% | 1.96/3.10 |
| bars | conflictivo | 0.166/0.223, 0.119/0.187 | 17.7%/3.9% | 0.594/0.889 | 6.7%/8.5% | 0.97/1.82 |
| beat_flash | conflictivo | 0.292/0.241, 0.256/0.209 | 0.2%/0.2% | 0.644/0.936 | 6.6%/8.3% | 1.48/2.01 |
| spectrum | consistente | 0.349/0.293, 0.364/0.282 | 3.0%/1.4% | -0.059/0.184 | 0.2%/0.6% | 1.80/1.87 |
| sustain | redundante | 0.000/0.000, 0.000/0.000 | 100.0%/100.0% | 1.000/1.000 | 6.7%/9.4% | 1.00/1.00 |
| idle | consistente | 0.349/0.197, 0.329/0.131 | 0.0%/0.0% | --/-- | 0.0%/0.0% | 0.25/0.38 |

### Pared: idle

| Techo | Clase | D media/mediana S/B | <.02 S/B | r S/B | F S/B | T/P S/B |
|---|---|---|---|---|---|---|
| combo | consistente | 0.312/0.264, 0.234/0.204 | 0.0%/0.0% | --/-- | 0.0%/0.0% | 3.58/3.23 |
| harmony | consistente | 0.743/0.752, 0.739/0.740 | 0.0%/0.0% | --/-- | 0.0%/0.0% | 7.91/8.12 |
| bars | consistente | 0.328/0.330, 0.256/0.258 | 0.0%/0.0% | --/-- | 0.0%/0.0% | 3.93/4.77 |
| beat_flash | consistente | 0.422/0.360, 0.321/0.274 | 0.0%/0.0% | --/-- | 0.0%/0.0% | 5.98/5.27 |
| spectrum | consistente | 0.678/0.426, 0.691/0.373 | 0.0%/0.0% | --/-- | 0.0%/0.0% | 7.28/4.89 |
| sustain | consistente | 0.349/0.197, 0.329/0.131 | 0.0%/0.0% | --/-- | 0.0%/0.0% | 4.04/2.62 |
| idle | redundante | 0.000/0.000, 0.000/0.000 | 100.0%/100.0% | --/-- | 0.0%/0.0% | 1.00/1.00 |

Los siete espejos son redundantes de forma exacta: `D=0` en 100% de frames.
La jerarquia deseada (techo/pared ~1.25--1.67) no aparece de forma estable en
ningun par consistente: debe aplicarse ganancia por canal, no inferirse del
look. Por ejemplo, `beat_flash/harmony` queda en 0.76/0.65 y
`spectrum/sustain` en 0.56/0.53.

## Aptitud cenital sobre audio real

La cota declarada es salto de brillo <=0.03/frame. Tabla: media, p99 y maximo
del salto por frame, tambien como `summer/billie`.

| Look | Media S/B | P99 S/B | Max S/B | Veredicto cenital |
|---|---:|---:|---:|---|
| combo | 0.0512/0.0445 | 0.2872/0.2587 | 0.4743/0.5533 | no cumple |
| harmony | 0.0103/0.0173 | 0.0645/0.1702 | 0.4733/0.5134 | no cumple |
| bars | 0.0552/0.0593 | 0.3099/0.3901 | 0.6236/0.5533 | no cumple |
| beat_flash | 0.0774/0.0631 | 0.4509/0.4085 | 0.6236/0.4173 | no cumple |
| spectrum | 0.0197/0.0350 | 0.1239/0.3901 | 0.3990/0.4957 | no cumple |
| sustain | 0.0303/0.0331 | 0.2562/0.2450 | 0.3149/0.3107 | no cumple |
| idle | 0.0000/0.0000 | 0.0000/0.0000 | 0.0000/0.0000 | cumple |

La conclusion incomoda es que solo `idle` cumple en ambos temas. `harmony`
tiene la menor media no-idle, pero sus maximos 0.473/0.513 siguen muy por
encima de 0.03. Esto es confort (no una afirmacion sobre riesgo fotosensible):
los pulsos musicales estan alrededor de 2 Hz, bajo la banda de 3--30 Hz.

## Desfase pared -> techo

El periodo medido es 468.9 ms en summer (128.0 BPM) y 513.9 ms en billie
(116.8 BPM). Los retrasos comparados son:

| Desfase | Summer | Billie | Contra suelo Zigbee de 40 ms |
|---|---:|---:|---|
| fijo 60 ms | 0.128 beat | 0.117 beat | visible por poco |
| fijo 100 ms | 0.213 beat | 0.195 beat | visible |
| fijo 150 ms | 0.320 beat | 0.292 beat | visible |
| 1/16 beat | 29.3 ms | 32.1 ms | invisible |
| 1/8 beat | 58.6 ms | 64.2 ms | visible por poco |
| 1/4 beat | 117.2 ms | 128.5 ms | visible |

**Veredicto: no anadir desfase por defecto.** El techo y la pared estan a la
vista a la vez: 60 ms/1-8 es apenas distinguible tras Zigbee, y 100--150 ms o
1/4 beat crean una desincronizacion relativa clara sin mejorar el enganche con
el audio. Si se quisiera probar una cascada deliberada, la unica unidad que
mantiene el gesto musical entre 117 y 128 BPM es techo retrasado **1/8 de
beat**; no un numero fijo de milisegundos. No se recomienda para el preset
normal.

## Recomendacion para este cuarto

Ninguno de estos pares ajusta por si solo el peso pared 0.6--0.8 / techo 1.0;
las tres pruebas requieren ganancia por canal. Aun asi, este es el orden de
prueba por separacion y baja coincidencia de destellos:

1. **Pared `beat_flash`, techo `harmony`**. `F=0.2%/0.7%`,
   `r=0.004/0.243`, `D=0.495/0.509`; pared es el acento y techo el ambiente.
   Subir techo aproximadamente 1.3--1.5x por su `T/P=0.76/0.65`.
2. **Pared `combo`, techo `harmony`**. `F=0.3%/1.8%`,
   `r=0.116/0.398`, `D=0.451/0.498`. Mantiene color espectral local y armonia
   cenital, pero pide mas ganancia del techo (`T/P=0.45/0.40`).
3. **Pared `spectrum`, techo `sustain`**. `F=0.2%/0.6%`,
   `r=-0.059/0.184`, `D=0.349/0.293`; es la alternativa menos ritmica. Exige
   elevar techo, pues `T/P=0.56/0.53`.

El par que no usaria nunca es **`beat_flash`/`beat_flash`**: es espejo exacto
(`D=0` en 100%) y a la vez tiene el mayor destello simultaneo, 22.2% en
summer y 16.2% en billie. Duplica el golpe sin dar informacion espacial.
