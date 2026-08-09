# Hue BPM Sync

Sincronizador de luces Philips Hue con deteccion de BPM en tiempo real desde el
audio de salida de Windows, por la Entertainment API (streaming DTLS, no la
REST lenta).

Funciona de extremo a extremo: `run.py sync` captura el audio del sistema,
detecta el tempo, predice el proximo beat y manda color a las luces a 50 Hz.

## Estado

| Fase | Contenido | Estado |
|------|-----------|--------|
| 1 | Captura WASAPI + ODF + tempo + PLL + monitor | **hecho** |
| 2a | Registro y CLIP v2 (credenciales, entertainment areas) | **hecho y verificado** |
| 2b | DTLS-PSK + HueStream (el streaming en si) | **hecho y verificado** |
| 3 | Efectos y loop de sincronizacion | **hecho** |
| 3b | Calibrar la compensacion de latencia contra la luz real | pendiente |
| 4 | Reconexion, idle, watchdog | **hecho** (sin probar cortes reales) |

## Instalacion

Requiere **Python 3.11 o superior**. No hay extensiones nativas en el camino
critico, asi que no depende de que nadie publique wheels.

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

## Uso

```powershell
# Valida el detector contra ground truth sintetico. No necesita audio ni luces.
.\.venv\Scripts\python.exe run.py selftest

# Lista los dispositivos loopback WASAPI.
.\.venv\Scripts\python.exe run.py devices

# BPM y beats en vivo desde lo que este sonando.
.\.venv\Scripts\python.exe run.py monitor

# Graba el audio del sistema, para afinar contra material real y repetible.
.\.venv\Scripts\python.exe run.py record summer.wav --seconds 25

# Analiza un WAV y explica por que eligio ese tempo.
.\.venv\Scripts\python.exe run.py analyze summer.wav --bpm 128
```

### Lo principal

```powershell
# Luces sincronizadas con lo que suene en el PC.
.\.venv\Scripts\python.exe run.py sync

# Igual pero sin bridge, para ver el efecto en consola.
.\.venv\Scripts\python.exe run.py sync --dry-run --mode beat_flash
```

Modos: `combo` (por defecto), `harmony`, `bars`, `beat_flash`, `spectrum`.

### Bridge (una sola vez)

```powershell
# Pulsa el boton redondo del bridge justo despues de lanzarlo.
.\.venv\Scripts\python.exe run.py register --ip 192.168.1.50

# Lista las entertainment areas de un bridge ya registrado.
.\.venv\Scripts\python.exe run.py areas

# Streaming real a las luces: barrido de color y flashes.
.\.venv\Scripts\python.exe run.py huetest --seconds 12
```

`register` escribe `hue_config.json` con `bridge_ip`, `username` y `clientkey`,
verifica las credenciales leyendo las entertainment areas y guarda el id del
area si solo hay una. Ese fichero esta en `.gitignore` y es el unico sitio
donde viven las credenciales: no hay ninguna hardcodeada en el codigo.

El `clientkey` es la PSK del handshake DTLS. Solo se emite si se pide
`generateclientkey` en el registro, y sin el no hay Entertainment API — de ahi
que reutilizar un `username` viejo de la API v1 no sirva.

Si se queda en `SILENCIO` con `frames 0`, el dispositivo por defecto no es
donde suena la musica (pasa con dispositivos virtuales tipo Steam o Discord).
Mira `run.py devices` y fija el nombre en `config.yaml`:

```yaml
audio:
  device_name: "JBL Charge 6"
```

Por nombre y no por indice a proposito: **los indices de WASAPI se renumeran**
en cuanto conectas o desconectas cualquier dispositivo de audio, asi que un
indice fijado en la configuracion deja de valer al enchufar unos auriculares.

## Arquitectura

```
audio/     capture.py      loopback WASAPI -> ring buffer (hilo de PortAudio)
           ringbuffer.py   buffer circular con contador global de muestras

analysis/  odf.py          STFT -> flujo espectral + energia por bandas
           tempo.py        autocorrelacion -> BPM y fase
           beatclock.py    PLL de fase, prediccion del proximo beat
           downbeat.py     histograma de energia -> cual beat es el "1"
           chroma.py       12 clases de altura -> color por armonia
           bands.py        normalizacion adaptativa graves/medios/agudos

hue/       rest.py         CLIP v2: registro, areas, start/stop de la sesion
           backends.py     DTLS-PSK + serializacion HueStream
           client.py       sesion completa, keepalive y reconexion

effects/   base.py         RenderContext, envolvente del beat, mezcla de color
           modes.py        combo | harmony | bars | beat_flash | spectrum | idle

engine.py                  orquestador: audio -> AudioState publicado
state.py                   estado compartido, publicado por swap atomico
timing.py                  temporizacion sub-ms en Windows
config.py                  config.yaml + hue_config.json
```

Tres hilos:

1. **Callback de WASAPI** — hace downmix a mono y escribe al ring buffer. Nada
   mas: cualquier analisis aqui hace que PortAudio suelte bloques.
2. **Analisis** — drena el buffer, calcula ODF a ~188 fps, estima tempo a 2 Hz,
   actualiza el PLL.
3. **Render** — corre a 50 Hz, consulta el reloj, evalua el efecto y emite el
   paquete HueStream.

## Por que un PLL y no deteccion reactiva

El Hue Sync oficial reacciona: detecta energia y responde. Eso impone un suelo
de latencia igual a la suma de captura + analisis + red + Zigbee.

Aqui el `BeatClock` es un oscilador de fase de rodadura libre que se corrige
contra las estimaciones del tracker. Eso permite preguntar en cualquier
instante:

```python
clock.time_to_next_beat(now)   # segundos hasta el proximo beat
clock.phase(now)               # posicion dentro del beat, 0..1
```

Como el proximo beat se conoce *antes* de que ocurra, el comando puede emitirse
por adelantado (`render.latency_compensation_ms`) y llegar a la luz justo a
tiempo. Un sistema reactivo no puede hacer esto por construccion.

## Resultados del self-test

Sobre patrones sinteticos de 30 s con ground truth exacto. El error es la
distancia entre el beat predicho y el beat real:

| caso | real | detectado | error medio | p90 |
|------|------|-----------|-------------|-----|
| house 128 | 128.0 | 127.9 | 4.0 ms | 5.3 ms |
| hip-hop 90 | 90.0 | 90.0 | 5.5 ms | 5.5 ms |
| dnb 174 | 174.0 | 173.7 | 1.0 ms | 1.7 ms |
| balada 76 | 76.0 | 152.0 (x2) | 7.8 ms | 8.9 ms |
| 128 + jitter 8 ms | 128.0 | 128.2 | 12.3 ms | 24.7 ms |
| 128 + ruido | 128.0 | 127.9 | 1.6 ms | 2.6 ms |
| 100 + jitter + ruido | 100.0 | 99.9 | 6.2 ms | 12.7 ms |

Enganche en ~3 s.

### Validacion con musica real

Calvin Harris — *Summer* (128 BPM real), capturado por loopback:

- **128.0 detectado**, estable desde los 3.0 s y sin oscilar en todo el tramo.
- En la tabla de candidatos el correcto gana 0.855 contra 0.371 del segundo:
  no esta cerca de dudar.
- Confianza entre 0.29 y 1.00 segun el pasaje. El z del pico sobre el fondo de
  la curva es ~8-19 en musica real, contra ~46 en el self-test sintetico. De
  ahi salen `salience_scale`, `min_confidence` y `full_confidence`, que estan
  calibrados contra esta grabacion y no contra el self-test.

Sobre los primeros segundos: en la intro el detector lee 88 BPM, no 128. No es
un fallo — ese tramo tiene otro pulso percibido, y analizando desde `--start 8`
engancha a 128 en 3 s. Sirve de recordatorio de que el self-test sintetico no
sustituye a `record` + `analyze` sobre material real.

Sobre el caso de la balada: engancha a la octava (152 en vez de 76). Para luces
eso sigue viendose sincronizado, porque un flash de cada dos cae en el pulso.
Lo que si arruina el efecto es una relacion no entera, y el self-test
distingue los dos casos explicitamente.

## Notas de implementacion no obvias

Cosas que costaron encontrar y conviene no deshacer sin medir:

- **Autocorrelacion sesgada, no insesgada.** Dividir por el solape de cada lag
  infla los lags largos y hace que el refuerzo armonico premie tempos falsos.
- **Armonicos muestreados en un entorno, no en el bin exacto.** El periodo real
  casi nunca cae en un lag entero; muestrear en `k*lag` falla el pico por
  redondeo y el error crece con `k`. Esto solo hacia que un tema a 174 BPM se
  detectara como 116.
- **La ventana de la media movil debe cubrir varios beats.** Con 0.35 s (~65
  frames) actuaba como un notch justo en la frecuencia del pulso a 174 BPM.
- **ODF de graves para el tempo.** Los hi-hats marcan corcheas y llevan al
  detector a la octava de arriba; bombo y caja marcan el pulso real.
- **El compas se mide con energia cruda de graves, no con la ODF.** La ODF
  esta log-comprimida (`log1p(1000*|X|)`), que es justo lo que la hace
  invariante al volumen y permite seguir el tempo con la musica bajita. Esa
  misma compresion aplasta la diferencia entre un bombo normal y uno acentuado.
  Y se toma el **pico** de la banda, no la suma: el acento es un transitorio y
  sumarlo sobre el beat entero lo diluye entre el bajo sostenido.
- **La confianza es un z-score robusto, no la autocorrelacion cruda.** La
  correlacion absoluta depende del material: un click sintetico da 0.8 y una
  pista producida da 0.3 con el pulso igual de claro, porque el sidechain y la
  reverb llenan la ODF. Lo comparable es cuanto sobresale el pico sobre el
  fondo de la curva.
- **`timeBeginPeriod(1)` en Windows.** Sin eso `time.sleep` tiene granularidad
  de ~15.6 ms y un loop a 50 Hz es imposible. Con eso, el jitter medido es de
  0.00 ms de media y 0.35 ms de maximo.

## Por que hay dos backends DTLS

Medido contra el bridge real (BSB002, firmware 1.78.0):

| backend | resultado |
|---------|-----------|
| `pure` (por defecto) | 600 paquetes, 0 fallos, 50.0 Hz |
| `mbedtls` | el bridge nunca responde al ClientHello |

La causa esta en una linea del log del backend que funciona:

    DTLS handshake ServerHello timeout, resending cookie ClientHello

El bridge exige el intercambio de cookie de DTLS (`HelloVerifyRequest`) y el
primer flight se pierde. El backend puro-python reenvia el ClientHello con la
cookie; python-mbedtls, a traves de su envoltorio de socket, no retransmite
nunca, asi que el handshake muere en silencio. El sintoma —cero respuesta— es
identico al de un bridge caido, y por eso costo tanto encontrarlo.

Descartados por el camino, todos por medicion: formato del paquete (verificado
byte a byte), secuencia de arranque (cuatro variantes), cifrado y version DTLS
(los 48 cifrados PSK y DTLS 1.0-1.2), interfaz de salida, firewall de Windows
(DNS por UDP funciona desde el mismo proceso), Hue Sync compitiendo, area
concreta corrupta y reinicio del bridge.

Leccion de esa caza, por si vuelve a pasar algo parecido: durante la
depuracion se valido el cliente mbedtls contra un servidor DTLS local y pasaba
sin problema. No demostraba nada util, porque usaba python-mbedtls en los dos
extremos y ninguno exigia cookie. Una prueba de loopback comprueba coherencia
interna, no interoperabilidad.

Conviene tener Hue Sync cerrado al probar: compite por la misma entertainment
area.

Cuando vuelva a conectar, queda calibrar `render.latency_compensation_ms`
contra las luces reales. Los 120 ms actuales son una estimacion, no una medida.

## Los efectos

`combo`, el modo por defecto, separa las dos dimensiones a proposito: **el
color dice que suena** (mezcla de graves/medios/agudos) y **el brillo dice
cuando** (envolvente del beat). Juntarlas produce un estrobo; separarlas se lee
como musica.

La envolvente se calcula de la *fase* del beat, no de eventos "hubo un beat".
Por eso puede subir el brillo durante la fraccion `beat_attack` ANTERIOR al
golpe. Combinado con `latency_compensation_ms`, el comando sale del PC antes
del beat y la luz enciende justo en el.

`bars` va un paso mas alla y usa el compas: la paleta avanza en el "1" de cada
compas y vuelve a empezar cada frase, asi que se ve el 4x4 de la musica en vez
de un parpadeo uniforme. Ademas, en todos los modos el downbeat pega mas fuerte
que el resto de tiempos (`downbeat_accent`).

Cuando no hay evidencia suficiente de donde cae el compas, los efectos degradan
a tratar todos los beats por igual. Acentuar un tiempo al azar se ve peor que
no acentuar ninguno.

Un efecto es una funcion pura de `RenderContext` a colores: no guarda estado,
no sabe de audio ni de DTLS. Anadir un modo es anadir una clase a
`effects/modes.py`.

## Que rinde el modo `harmony`

El color deja de responder al timbre de la mezcla y responde a que notas
suenan. Medido:

| material | tonalidad detectada |
|----------|---------------------|
| acordes sintetizados | 0.20 - 0.41 |
| musica real (mezcla completa) | 0.04 - 0.05 |
| ruido blanco | 0.008 |

Identifica las 12 notas sueltas y todas las notas de triadas, septimas y
quintas, con armonicos incluidos. Volver al mismo acorde devuelve el mismo
color.

El brillo se comporta distinto que en los demas modos, y hicieron falta dos
cambios para que el modo sirva de algo en la practica:

**Menos profundidad.** Con la misma pulsacion que `combo` el parpadeo domina la
percepcion y el color pasa desapercibido, asi que ambos modos se ven identicos
aunque el color sea distinto.

**Envolvente sinusoidal en vez de pico.** Bajar la profundidad no basta: los
flancos agudos de la envolvente normal se siguen leyendo como destellos. Medido
a 120 BPM y 50 fps, el brillo saltaba 0.150 por frame con la envolvente de pico
y 0.031 con el coseno, y eso con MAS rango de brillo. Lo que importa es la
forma, no la profundidad.

**Brillo constante por defecto, y pendiente acotada por tempo.** Ni siquiera el
coseno suave acaba de funcionar: cualquier bajada entre cambios de color se
percibe como un apagado en vez de como parte de la musica, asi que
`harmony_beat_depth` viene a cero y solo cambia el color. Si se le sube, la
profundidad se recorta sola para que el salto por frame no pase de
`harmony_max_step`. Hace falta porque la fase avanza (BPM/60)/fps por frame:
un ajuste comodo a 120 BPM parpadea a 174.

**El modo se aparta cuando no hay armonia fiable, y eso es casi siempre en
mezcla densa.** Con el umbral bajo el color perseguia un centroide que da 4.84
vueltas al circulo cromatico en 22 segundos sobre Billie Jean: ningun tema
cambia de acorde a ese ritmo, era ruido pintado de color. Subiendo
`harmony_min_tonality` a 0.08 el movimiento cae a 0.0004 por frame, o sea que
el color simplemente se queda quieto y manda el espectral.

Antes de dar con eso se probaron dos cosas que **no** funcionan, anotadas para
que nadie las repita. Cuantizar a la clase de altura dominante con histeresis,
que es lo que arreglo el compas: en una triada las tres notas pesan casi igual
y el maximo es una moneda al aire, asi que sobre una progresion con 3 cambios
reales la clase dominante cambiaba 11 veces. Y suavizar fuerte el color, que
cuesta precision sin comprar estabilidad: volver al mismo acorde daba un color
desviado 0.24 en el circulo contra 0.09 sin suavizado.

**En mezcla completa la ganancia de estabilidad de color es modesta.** El color resulta un 15% mas
estable que el espectral (0.016 contra 0.019 de movimiento por frame), no el
salto que sugiere la prueba sintetica. La bateria reparte energia por las 12
clases y aplana el chroma, asi que la tonalidad de una mezcla real queda mucho
mas cerca del ruido que de un acorde limpio. Donde de verdad luce es en
material tonal y poco denso.

Coste: 1.4% de un nucleo sobre lo que ya habia.

## Limites del seguimiento de compas

Medido sobre grabaciones reales, no sobre sintetico:

| tema | confianza | resultado |
|------|-----------|-----------|
| Billie Jean (backbeat claro) | 0.133 | engancha, marcado **AMBIGUO** |
| Summer (house four-on-the-floor) | 0.051 | no engancha, correctamente |

Dos limitaciones que conviene tener presentes:

**Ambiguedad de medio compas.** El patron mas comun del pop y el rock pone el
bombo en el 1 y en el 3 con la misma fuerza. Se detecta la rejilla del compas
sin problema —esos dos tiempos se llevan el 70% de la energia frente al 30% de
los otros dos— pero no hay forma de saber cual de los dos empieza el compas.
El efecto puede acabar cambiando de color en el 3. Se nota, pero sigue siendo
ritmico y consistente. `sync` lo marca con un `?` junto al numero de compas y
`analyze` lo dice explicitamente.

**No funciona en four-on-the-floor.** En house y buena parte del EDM el bombo
pega exactamente igual en los cuatro tiempos: no hay acento por tiempo que
medir. Eso no es un fallo de la grabacion, es la definicion del genero. El
compas ahi se marca con cambios de armonia y estructura cada 8 o 16 compases,
que es territorio de los issues #7 y #8. Cuando no hay enganche los efectos
degradan a tratar todos los beats por igual.

**La estabilidad importa mas que el acierto.** La primera version usaba un
solo umbral y en vivo la confianza oscila entre 0.03 y 0.27 sobre el mismo
tema, asi que enganchaba y desenganchaba cada pocos segundos y el "1" saltaba
de posicion. El color cambiaba en un tiempo distinto cada vez, que se ve peor
que no cambiarlo nunca. Con histeresis (0.14 para enganchar, 0.07 para soltar)
y exigiendo 8 compases antes de mover el downbeat, los cambios de posicion
pasaron de 13 a 0 sobre la misma grabacion.

**El umbral sigue siendo el parametro mas fragil del proyecto**, calibrado
sobre dos canciones. Si aparece material que engancha cuando no deberia, es el
primer sitio donde mirar.

## Nota de diseno: numero de canales

Las dos entertainment areas del bridge (`bed` y `Baño`) tienen **un solo canal
cada una**. Con un canal no hay mapeo espacial posible: los efectos se reducen
a color y brillo en el tiempo, sin barridos ni izquierda/derecha. El codigo ya
soporta N canales, pero no tiene sentido invertir en efectos espaciales hasta
que haya mas luces en un area.
