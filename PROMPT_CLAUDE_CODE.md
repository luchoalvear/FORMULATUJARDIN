# Prompt para Claude Code — Sistema de Formulación EPI JUNJI/Educación Parvularia

---

## ⚠️ INSTRUCCIONES DE USO — LEER ANTES DE EJECUTAR

Este prompt describe un sistema web grande (un único archivo HTML de más de 7.000 líneas). Sigue esta secuencia para evitar que Code genere código incompleto.

**PASO 1 — Pide el esqueleto primero (antes de pegar este prompt)**

Dile a Code:
> "Antes de implementar la lógica, genera el esqueleto completo del archivo HTML: estructura de navegación, sidebar con los 9 pasos, header, layout general, todas las funciones vacías con sus nombres y parámetros definidos, y el estado global APP_STATE completo. Sin lógica de cálculo aún. Archivo: sistema_formulacion_epi.html"

**PASO 2 — Pega este prompt completo**

Con el esqueleto ya generado, pega todo este documento y agrega al inicio:
> "Implementa la lógica completa según este spec, respetando el esqueleto que ya generaste en sistema_formulacion_epi.html"

**PASO 3 — Si Code se corta a la mitad**

Dile exactamente:
> "El archivo quedó incompleto, falta implementar desde el módulo X. Continúa editando sistema_formulacion_epi.html desde la función [nombre de la última función visible en el archivo]."

Code leerá el archivo y continuará sin reescribir lo anterior.

**PASO 4 — Verificación final**

Al terminar, pídele:
> "Revisa el archivo completo y verifica: (1) que no haya funciones llamadas pero no definidas, (2) que todos los módulos del sidebar estén conectados a sus funciones de render, (3) que el cálculo de CAE con los datos de Las Cuncunitas (ICov=0.87, ICal=0.45, 96 cupos, superficie 632m², HA) devuelva un CAE cercano a los valores de referencia de la demo, (4) que la Dotación Teórica según Decreto 181 con los cupos de Cuncunitas (40 SC + 56 NM) reproduzca exactamente 9 cargos calculados, (5) que Gastos Administrativos y Material Didáctico con situación actual real (313 m², 84 cupos) reproduzcan $15.861.922 y $34.285.714 respectivamente."

**LO QUE NO HACER:**
- No pidas "hazlo todo de una vez" sin el esqueleto previo
- No pidas archivos separados por módulo — la integración posterior es más trabajo
- No interrumpas una generación en curso — deja que termine

---

## INSTRUCCIÓN GENERAL

Construye una aplicación web completa en **un único archivo HTML** (`sistema_formulacion_epi.html`, con CSS y JS embebidos) que digitalice el proceso de formulación de Estudios Preinversionales (EPI) para proyectos de infraestructura de jardines infantiles y salas cuna bajo la metodología del SNI (Sistema Nacional de Inversiones) de Chile, para JUNJI, SLEP e INTEGRA. El frontend es un único HTML (sin build step), usando:

- **Bootstrap 5** (CDN) para layout y componentes
- **Bootstrap Icons** (CDN)
- **Leaflet.js** (CDN) para mapas OpenStreetMap
- **Chart.js** (CDN) para gráficos
- **ExcelJS** (CDN, UMD) para exportar planillas `.xlsx` con fórmulas y formato
- **docx.js** (CDN, build UMD de `dolanmiu/docx`) para generar documentos `.docx` reales (certificados, memorias, modelo de gestión)
- **Claude API** (Anthropic) para el asistente redactor, vía un **proxy local** (`proxy_claude.py`) que evita el bloqueo CORS del navegador — el usuario ingresa su API key en Configuración
- **Backend local propio** (`backend_epi.py`, Python stdlib + SQLite) para autenticación real de usuarios, persistencia de proyectos por cuenta, y almacenamiento de documentos adjuntos — ver sección **AUTENTICACIÓN Y BACKEND**
- **localStorage** solo como respaldo para el modo demo/invitado (sin cuenta) y para configuración local del navegador (API key)

El diseño debe ser profesional, limpio, en español, con identidad visual institucional (colores JUNJI: azul `#003366` + amarillo `#FFB800`). Responsivo para desktop (mínimo 1280px), con soporte de layout ancho (≥1440px) para que el mapa y las tablas usen bien el espacio.

Todo texto generado por IA debe salir en **texto plano, sin Markdown** (nada de `#`, `**`, guiones de lista) — ver **INSTRUCCION_SIN_MARKDOWN** en Módulo 8/9.

---

## ARQUITECTURA GENERAL

### Estado global de la aplicación

```javascript
let APP_STATE = {
  user: { id, nombre, username, rol, institucion, slep }, // null en modo demo/invitado
  proyecto_id: null, // id del proyecto en el backend; null si es modo demo/invitado (solo local)
  config: { anthropic_api_key: '', version: '1.0' },
  ui: { modulo_actual: 1, modulos_completados: [] },
  proyecto: {
    nombre, bip, institucion, slep, region, provincia, comuna, sector,
    tipo_proceso, // Construcción | Ampliación | Reposición | Normalización | Mejoramiento | Conservación | Habilitación
    nombre_editado_manual: false,
    arbol_decision: null,
    nivel_proporcionalidad: null, // 'exento' | '0' | '1' | '2' (según monto UTM del proyecto)
    etapa: 'diseño', // 'diseño' | 'ejecucion'
    actualizacion_diseno: { activa: false, /* ... */ },

    establecimiento: { nombre, rbd, codigo_gesparvu, direccion, lat, lng, vecinos: [] },

    diagnostico: {
      icov: { niveles: {}, resultado: null, metodo: 'manual', red: { codigo_estudio: null, jardines: [] } },
      ins: { resultado: null }
    },
    ical_detallado: { respuestas: {}, resultado: null }, // no aplica si tipo_proceso === 'Construcción'

    programa_arq: { zona_climatica, cupos_sc, cupos_nm, n_pisos, recintos, superficie_total, superficie_actual },

    equipamiento: { precios_unitarios: {}, planilla: [], total_neto: 0, total_con_iva: 0 },

    alternativas: [ /* ver Módulo 7 */ ],
    evaluacion: { alternativa_ganadora: null, alternativas: [] },
    costos_om: {
      personal: { actual: 0, proyecto: 0 },
      material_didactico: { actual: 0, proyecto: 0 },
      gastos_administrativos: { actual: 0, proyecto: 0 },
      mant_prev_actual: 0,
      mant_corr_actual: 0
    },
    costos_privados: { oocc: 0, consultoria: 0, terreno: 0, equipamiento: 0, total_i0: 0 },
    costos_sociales: { oocc: 0, consultoria: 0, terreno: 0, equipamiento: 0, total_i0_social: 0 },
    ris_umbral: null,

    conservacion: { /* ver Módulo 5-Conservación */ },
    certificacion: { director_nombre: null, director_cargo: null },

    redaccion: { introduccion: '', area_estudio: '', establecimiento_foco: '', area_influencia: '', diagnostico: '', alternativas: '', evaluacion_economica: '', conclusion: '' },
    apoyo_redaccion: { area_estudio: { indicadores: [] }, area_influencia: { indicadores: [] } },

    modelo_gestion: {
      ejes: { institucional: '', rrhh: '', materiales: '', financiero: '', mantencion: '', continuidad: '', calidad: '' },
      dotacion: [],   // { cargo, dotacion_actual, costo_actual_anual, dotacion_proyectada }
      cronograma: [], // { hito, plazo }
      riesgos: [],    // { riesgo, efecto, mitigacion }
      salarios_dto181: {},           // { [cargo_id]: costo_anual_por_persona }
      grados_dto181: {},             // { [cargo_id]: { categoria, grado } }
      valor_uf_remuneraciones: 39727.96, // UF del 31-12 del año anterior
      fecha_uf_remuneraciones: '2025-12-31'
    }
  }
}
```

**Persistencia (ver detalle en AUTENTICACIÓN Y BACKEND):**
- Si `APP_STATE.proyecto_id` está definido (cuenta real con proyecto abierto), `{ proyecto, ui }` se guarda vía `PUT /api/proyectos/:id` contra `backend_epi.py`.
- Si `APP_STATE.proyecto_id` es `null` (modo demo/invitado), `APP_STATE` completo se guarda en `localStorage` (`epi_sistema_data`).
- `APP_STATE.config.anthropic_api_key` siempre se guarda aparte en `localStorage` (`epi_config`), independiente de la cuenta.
- El token de sesión se guarda en `localStorage` (`epi_token`).
- `guardarEstadoConDebounce()` (500ms) es el punto de entrada usado en **todo** el código al editar cualquier campo.

**Migración de estado (`fusionarProfundo`):** cada vez que se agrega un campo nuevo a `APP_STATE.proyecto` (como pasó con `modelo_gestion`, `programa_arq.superficie_actual`, etc.), los proyectos ya guardados deben seguir abriendo sin errores. Implementar `fusionarProfundo(base, sobrescribir)` — deep-merge recursivo que rellena claves faltantes del objeto base (`PROYECTO_DEFECTO`, un `JSON.parse(JSON.stringify(...))` tomado de `APP_STATE.proyecto` justo después de definir su forma completa) sobre el proyecto cargado desde backend/localStorage, sin pisar valores ya guardados.

---

## AUTENTICACIÓN Y BACKEND (piloto local, con vista a migración web)

### Arquitectura

- **Frontend:** `sistema_formulacion_epi.html`, un único archivo. Agrega llamadas `fetch` al backend.
- **Backend:** `backend_epi.py`, servidor HTTP con librería estándar de Python (`http.server`, `sqlite3`, `hashlib`, `secrets`), sin dependencias externas. Corre en `http://localhost:8790`.
- **Base de datos:** SQLite, archivo `epi_sistema.db` (se crea solo). Tablas: `usuarios`, `sesiones`, `proyectos`, `documentos`.
- **Para correrlo:** `py backend_epi.py` en una terminal aparte. Sin el backend corriendo, el login con cuenta real falla con un toast explicativo; el modo demo/invitado sigue funcionando sin él.
- **Proxy de Claude:** `proxy_claude.py`, servidor aparte en `http://localhost:8787`, reenvía `POST /v1/messages` a la API de Anthropic agregando el header CORS que el navegador necesita. El frontend llama a `http://localhost:8787/v1/messages`, nunca directo a `api.anthropic.com`.

### Modelo de datos (SQLite)

```sql
usuarios(id, nombre, username UNIQUE, password_salt, password_hash, institucion, rol, slep, fecha_creacion)
sesiones(token PRIMARY KEY, usuario_id, fecha_creacion, fecha_expiracion)  -- token vigente 30 días
proyectos(id, usuario_id, nombre, bip, data TEXT, fecha_creacion, fecha_modificacion)
-- data = JSON.stringify({ proyecto: APP_STATE.proyecto, ui: APP_STATE.ui })
documentos(id, proyecto_id, categoria, subcarpeta, nombre_archivo, tipo_mime, tamano_bytes, contenido_base64, fecha_subida)
```

Claves con `hashlib.pbkdf2_hmac('sha256', password, salt, 100_000)`; tokens con `secrets.token_hex(32)`. Subida de archivos vía JSON con el contenido en base64 (sin parsing multipart) — límite 40MB por archivo, validado en frontend antes de enviar.

### Endpoints REST (JSON, `Authorization: Bearer <token>` salvo login/registro)

| Método | Ruta | Body | Devuelve |
|--------|------|------|----------|
| POST | `/api/registro` | `{ nombre, username, password, institucion, rol, slep }` | `{ token, usuario }` |
| POST | `/api/login` | `{ username, password }` | `{ token, usuario }` |
| GET | `/api/me` | — | `{ usuario }` |
| GET | `/api/proyectos` | — | `{ proyectos: [{ id, nombre, bip, avance_pct, fecha_creacion, fecha_modificacion }] }` |
| POST | `/api/proyectos` | `{ nombre, data }` | `{ id }` |
| GET | `/api/proyectos/:id` | — | `{ id, nombre, data }` |
| PUT | `/api/proyectos/:id` | `{ data }` | `{ ok, fecha_modificacion }` |
| DELETE | `/api/proyectos/:id` | — | `{ ok }` |
| GET | `/api/proyectos/:id/documentos` | — | `{ documentos: [{ id, categoria, nombre_archivo, tamano_bytes, fecha_subida }] }` |
| POST | `/api/proyectos/:id/documentos` | `{ categoria, subcarpeta, nombre_archivo, tipo_mime, contenido_base64 }` | `{ id }` |
| GET | `/api/documentos/:id` | — | archivo binario (descarga) |
| DELETE | `/api/documentos/:id` | — | `{ ok }` |

`avance_pct` se calcula al listar como `modulos_completados.length / 9 * 100`.

### Flujo de sesión en el frontend

1. **Al cargar la página** (`inicializarSesion()`): valida token guardado vía `GET /api/me`; si es inválido, revisa si hay sesión local de invitado/demo antes de mostrar el login.
2. **Pantalla "Mis Proyectos"** (`#pantalla-proyectos`): lista proyectos de la cuenta vía `GET /api/proyectos`, con crear/abrir (fusiona `data` sobre estado limpio vía `fusionarProfundo`)/eliminar (confirmación de doble clic, nunca `confirm()` nativo).
3. **Dentro del dashboard**, header con botones "Mis Proyectos" (oculto en modo demo) y "Cerrar sesión".
4. **Guardado:** `guardarEstado()` decide backend vs `localStorage` según `APP_STATE.proyecto_id`.

### Patrón de confirmación de dos clics (usar en TODA acción destructiva)

Nunca usar `confirm()`/`prompt()` nativos (bloquean la UI, no automatizables). Patrón estándar:

```javascript
function confirmarAccion(id, btn) {
  if (btn.dataset.confirmando === '1') { ejecutarAccion(id); return; }
  btn.dataset.confirmando = '1';
  btn.dataset.textoOriginal = btn.textContent;
  btn.textContent = '¿Confirmar?';
  btn.classList.add('btn-danger'); btn.classList.remove('btn-outline-danger');
  setTimeout(() => {
    if (btn.dataset.confirmando === '1' && btn.isConnected) {
      btn.dataset.confirmando = '0';
      btn.textContent = btn.dataset.textoOriginal;
      btn.classList.remove('btn-danger'); btn.classList.add('btn-outline-danger');
    }
  }, 4000);
}
```

---

## FLUJO DE NAVEGACIÓN Y SIDEBAR (9 módulos)

Sidebar vertical con progreso (`.step-item[data-modulo="N"]`), **libremente navegable en cualquier orden** (no bloquea avanzar sin completar el módulo anterior):

1. Identificación del Proyecto
2. Localización y Mapa
3. Diagnóstico ICov (Cobertura)
4. Cumplimiento Normativo ICal
5. Programa Arquitectónico *(o "Certificado de Conservación" si `tipo_proceso === 'Conservación'`)*
6. Equipos y Equipamiento *(o "Estándares MINEDUC" si Conservación)*
7. Evaluación Económica (VAC/CAE) *(o "no aplica" si Conservación; o "Actualización Evaluación Económica" si `etapa === 'ejecucion'` con actualización de diseño activa)*
8. Redacción Asistida por IA
9. Resumen y Exportación (incluye el Modelo de Gestión)

`mostrarModulo(num)` decide el `render*()` correcto según `esProcesoConservacion(tipo_proceso)`, `nivel_proporcionalidad === 'exento'`, y `etapa/actualizacion_diseno`, actualiza el `<h2>` del encabezado dinámicamente para reflejar esas variantes (incluida la de Módulo 4 cuando `tipo_proceso === 'Construcción'`, ver más abajo), y llama `actualizarSidebar()` + `actualizarProgresoGeneral()` + `guardarEstadoConDebounce()`.

---

## MÓDULO 1 — IDENTIFICACIÓN DEL PROYECTO

Campos: Nombre del establecimiento, BIP, RBD/Código GESPARVU, Institución (select), SLEP (texto si aplica), Región/Provincia/Comuna/Sector (selects encadenados con `COMUNAS_CHILE`), Dirección, **Proceso de inversión** (select `PROCESOS_INVERSION = ["Construcción","Ampliación","Reposición","Normalización","Mejoramiento","Conservación","Habilitación"]`, con árbol de decisión Sí/No opcional de apoyo).

**Nombre generado automáticamente:** `PROCESO + " jardín infantil " + NOMBRE_ESTABLECIMIENTO + ", " + COMUNA`, editable manualmente (`nombre_editado_manual` evita que se siga autogenerando una vez editado a mano).

**Selector de Nivel de Proporcionalidad** (`nivel_proporcionalidad`): `exento` (<5.000 UTM, Nivel 0) | `0` | `1` | `2`. Condiciona fuertemente el Módulo 7 (ver Estudio Preinversional Simplificado) y oculta pasos del sidebar que no aplican para Nivel 0.

**Selector de Etapa** (`etapa`): `diseño` | `ejecución`. Si `ejecución` y el proyecto tiene un diseño previo aprobado, activa el toggle **"Actualización de Diseño"** (`actualizacion_diseno.activa`), que cambia el Módulo 7 a un modo sin comparación de alternativas (una sola alternativa ya decidida, solo se re-verifica el CAE con cifras actualizadas).

**Regla central — `esConstruccionNueva()`:**
```javascript
function esConstruccionNueva() {
  return APP_STATE.proyecto.tipo_proceso === 'Construcción';
}
```
`"Construcción"` es el único proceso donde el establecimiento **no existe todavía**: no hay infraestructura cuya calidad/nivel de servicio se pueda auditar (Módulo 4 no aplica), ni costos/dotación/superficie "actuales" que medir (Módulo 7). El resto de los procesos (Reposición, Ampliación, Normalización, Mejoramiento, Habilitación) parte de un establecimiento existente. Esta función se usa transversalmente — no se le pide al usuario que lo indique aparte, se deriva de `tipo_proceso`.

---

## MÓDULO 2 — LOCALIZACIÓN Y MAPA

### Mapa (Leaflet)

`#mapa` con `flex:1 1 auto` dentro de una columna `d-flex flex-column` para que llene el espacio disponible verticalmente (junto al panel lateral de vecinos, ambos a la misma altura). Tile layer OpenStreetMap estándar.

- **Marcador del establecimiento** (ícono propio), arrastrable — `actualizarMarcadorEstablecimiento(lat, lng)` actualiza `establecimiento.lat/lng` y el popup.
- **Radios de cobertura**: círculos de 500m/1000m.
- Sección **"Geocodificación"** con texto explicativo de qué hace (buscar la dirección escrita y ubicarla en el mapa automáticamente) — el campo `#mapa-direccion` tiene un listener `input` que persiste `establecimiento.direccion` de inmediato (evita que quede "stale" si el geocode falla o hay un re-render).

`geocodificar(direccion)`:
```javascript
async function geocodificar(direccion) {
  APP_STATE.proyecto.establecimiento.direccion = direccion; // persistir siempre, aunque falle
  const q = direccion.includes('Chile') ? direccion : direccion + ', Chile';
  const url = `https://nominatim.openstreetmap.org/search?q=${encodeURIComponent(q)}&format=json&limit=1&countrycodes=cl&addressdetails=1`;
  // en éxito: mover marcador y mostrar data[0].display_name en el toast (verificación visual del match)
  // en error/sin resultados: toast sugiriendo hacer click manual en el mapa
}
```

### Base de datos JUNJI/INTEGRA/Privados embebida

Embeber en el HTML (constantes globales, generadas desde `Insumos/Geo/UE Coordenadas.xlsx` y `Insumos/Geo/VTF.kmz`):
- `BD_JARDINES_COORDS`: `{ [codigo_gesparvu]: { lat, lng, ... } }` — ~3.000 jardines JUNJI con coordenadas reales.
- `BD_OTROS_ESTABLECIMIENTOS`: array `[nombre, lat, lng, tipo, comuna]` — ~2.000 establecimientos INTEGRA y privados con coordenadas reales.

`buscarVecinosDesdeBD(jardinEstudio)`: ubica primero el jardín en estudio y sus vecinos usando `BD_JARDINES_COORDS` por código (instantáneo, sin llamada de red); solo los establecimientos sin coordenada conocida se geocodifican con Nominatim como respaldo. El toast distingue "ubicados con coordenadas conocidas" de "geocodificando restantes".

**Buscador de vecinos manual**: `#vecino-buscar-otro`, autocompleta contra `BD_OTROS_ESTABLECIMIENTOS` por nombre, agrega con coordenadas reales al hacer click. Debajo, un formulario de coordenadas manuales como último respaldo ("O ingresa coordenadas manualmente:").

**Lista de establecimientos vecinos** (`renderListaVecinos`), un ítem por línea con el formato exacto:
```
• Jardín Infantil/Sala Cuna {nombre} — Capacidad: {N} cupos — {tipo}
```
donde `tipo` ∈ `JUNJI | Integra | Privado | VTF` (`tipoAdministracionJardin()`) y `capacidad` es la suma de `cap_sc + cap_nm + cap_tr + cap_het` (`capacidadTotalJardin()`); si no hay dato, mostrar "N/D".

---

## MÓDULO 3 — DIAGNÓSTICO ICov (COBERTURA)

**Niveles educativos** (`NIVELES_EDUCATIVOS`): SCM (Sala Cuna Menor, 0-1) | SCMy (Sala Cuna Mayor, 1-2) | NMM (Nivel Medio Menor, 2-3) | NMMy (Nivel Medio Mayor, 3-4) | NT1 (Pre-Kínder, 4-5) | NT2 (Kínder, 5-6).

Para cada nivel activo: **O_j** (oferta), **M_j** (matrícula), **LE_j** (lista de espera).

```
D_j_min = M_j + LE_j
ICov_j = D_j_min === 0 ? 1 : min(1, O_j / D_j_min)
w_j = D_j_min / Σ(D_k_min)
ICov = Σ(w_j × ICov_j)
```

**Método "Red" (área de influencia)**: alternativa a ingresar niveles manualmente — agrega jardines vecinos completos (con su propia matrícula/lista de espera/oferta por nivel) a `diagnostico.icov.red.jardines[]` y agrega todo antes de aplicar la misma fórmula ponderada. `calcularICovRed()` y `calcularICov()` (método manual) ambas deben llamar `calcularINS()` al terminar para mantener el INS sincronizado.

Semáforo: rojo <0.5, amarillo 0.5-0.8, verde >0.8.

---

## MÓDULO 4 — CUMPLIMIENTO NORMATIVO (ICal) + INDICADOR INS

### Excepción — Construcción nueva

Si `esConstruccionNueva()`, **no mostrar el checklist**: reemplazar todo el contenido del módulo por un aviso:
> "No aplica. Este proyecto corresponde a un establecimiento nuevo (tipología 'Construcción') — no existe infraestructura actual cuyo nivel de servicio (ICal) se pueda auditar. La justificación del proyecto se basa exclusivamente en el déficit de cobertura (ICov, Módulo 3)."

El encabezado del módulo (`mostrarModulo`) y el ítem del sidebar deben reflejarlo: "4. Cumplimiento Normativo (No aplica — Construcción)".

### Checklist ICal (cuando aplica)

`PLANILLA_ICAL`: array de categorías con `{ categoria, referencia, peso_categoria, items: [{ id, descripcion, peso_item }] }`, cubriendo DS N°548 (antecedentes legales, condiciones del terreno, emplazamiento, recintos mínimos, infraestructura y seguridad) y OGUC (accesibilidad universal, locales escolares, requisitos específicos). Cada ítem tiene estado `cumple` (1.0) | `parcial` (0.5) | `no_cumple` (0.0) | `na` (excluido del cálculo).

```javascript
function calcularICal(respuestas) {
  let puntaje_total = 0, peso_aplicable_total = 0;
  PLANILLA_ICAL.forEach(cat => cat.items.forEach(item => {
    const estado = (respuestas[item.id] || {}).estado || 'no_cumple';
    if (estado === 'na') return;
    peso_aplicable_total += item.peso_item;
    if (estado === 'cumple') puntaje_total += item.peso_item;
    else if (estado === 'parcial') puntaje_total += item.peso_item * 0.5;
  }));
  const ICal = peso_aplicable_total > 0 ? puntaje_total / peso_aplicable_total : 0;
  // guardar, renderResultadoICal(), calcularINS()
}
```

Exportar planilla imprimible (`exportarPlanillaICal`).

### Indicador INS

```javascript
function calcularINS() {
  const ICov = /* p.diagnostico.icov.resultado?.ICov ?? null */;
  if (ICov == null) { /* limpiar resultado, return */ }

  let ICal, INS;
  if (esConstruccionNueva()) {
    // no existe infraestructura cuyo nivel de servicio se pueda medir
    ICal = null;
    INS = ICov;
  } else {
    ICal = /* p.ical_detallado.resultado?.ICal ?? null */;
    if (ICal == null) { /* limpiar resultado, return */ }
    INS = ICal * ICov;
  }
  const deficit = 1 - INS;
  const interpretacion = deficit >= 0.60 ? 'Crítico' : deficit >= 0.40 ? 'Significativo' : deficit >= 0.20 ? 'Moderado' : 'Bajo';
  // guardar { ICov, ICal, INS, deficit, interpretacion }
}
```

El resumen (`renderResumenINS`) debe mostrar, cuando `ICal == null`: la fila de ICal como badge gris "No aplica" con la nota "Establecimiento nuevo — no medible", el título de la tabla como "Resumen de Indicadores de Cobertura" en vez de "INS", y un aviso explicativo arriba de la tabla.

---

## MÓDULO 5 — PROGRAMA ARQUITECTÓNICO (o CONSERVACIÓN)

### 5.A Programa Arquitectónico (procesos ≠ Conservación)

Inputs: zona climática, cupos Sala Cuna (`cupos_sc`), cupos Nivel Medio (`cupos_nm`), número de pisos. Genera automáticamente el programa de recintos (área docente por salas de 20 SC / 28 NM, área administrativa, área de servicios fijas) con fórmula de superficie total (recintos + 20% muros + circulaciones + escaleras si 2 pisos).

**Nuevo campo — `superficie_actual`**: m² del establecimiento existente (0 o vacío si el proyecto es de infraestructura nueva). Se pide y usa en el Módulo 7, no aquí — este módulo solo diseña la superficie **proyectada**.

### 5.B Conservación (si `tipo_proceso === 'Conservación'`)

Reemplaza Programa Arquitectónico y Evaluación Económica por un flujo propio, según el **Instructivo de Proyectos de Conservación de Infraestructura Pública (SNI)**:

**Diagnóstico del activo:** nombre del activo, diagnóstico de daño/deterioro (textarea), Tabla N°1 (capacidad máxima, nivel de utilización actual, % de uso calculado).

**Certificado 30%** (indicador central de Conservación — el costo de conservación no debe superar el 30% del costo de reposición del activo):
```
indicador = costo_conservacion / costo_reposicion * 100
```
Semáforo verde si ≤30%, rojo si >30% con alerta sugiriendo reclasificar el proceso.

`VALOR_REFERENCIAL_REPOSICION_UF_M2 = 55` (UF/m²) — **editable, no hardcodeado a fuego**: es el valor por defecto sugerido según Oficio N°276 MOP (01-07-2021), pero el campo queda abierto a edición porque el valor puede actualizarse en el futuro. Mostrar siempre la nota de la fuente (`NOTA_VALOR_REFERENCIAL_REPOSICION`) junto al campo.

**Memoria del Proyecto de Conservación (Anexo N°3)** — estructura oficial completa, con las siguientes secciones y tablas editables (estado en `proyecto.conservacion.memoria`):
1. Nombre del proyecto
2. Ubicación (comuna, distancia a referencia urbana, dominio del inmueble)
3. Diagnóstico
4. Descripción y justificación de las acciones de conservación (+ Plan de Contingencia opcional, + impactos diferenciados opcional)
5. Fotografías (referencia a "Documentos Adjuntos")
6. Definición del activo (unidad de medida) + **Tabla — Costo Reposición del Activo** (`tabla_reposicion[]`: identificación, magnitud m²/ml, valor referencial UF/m²·ml, costo total, usando `valor_uf`/`fecha_uf` editables del proyecto)
   6.1 **Tabla — Costo de Conservación**: A) Obras Civiles (`tabla_obras_civiles[]`: identificación, superficie a intervenir, valor unitario UF/m², costo total), B) Otras Asignaciones Presupuestarias (consultorías, equipamiento, equipos, otros gastos), C) Total
   6.3 Cumplimiento Indicador 30%

Función `sincronizarTotalesMemoriaConCertificado()`: botón que empuja los totales calculados de la Memoria hacia los campos del Certificado 30% (evita mantener dos fuentes desincronizadas manualmente).

Genera documento Word (`generarMemoriaConservacion()`) con la estructura exacta de arriba — usando UF/M$ (miles de pesos) como convención de la institución, no pesos directos.

**Documentos Adjuntos de Conservación**: categorías `CATEGORIAS_DOCUMENTOS_CONSERVACION` (fotografías, planimetría/planos, EETT y TDR, presupuestos detallados, cotizaciones de equipamiento, plan de contingencia, otros), cada una con su subcarpeta BIP correspondiente, tipos de archivo permitidos (PDF, imágenes JPG/PNG, Word/Excel, CAD DWG/DXF), tamaño máximo 40MB. Sube/lista/descarga/elimina vía los endpoints `/api/proyectos/:id/documentos`. Solo disponible si el proyecto está guardado en el backend (requiere cuenta real, no modo demo).

Genera también: **Certificado de Conservación** (`generarCertificadoConservacion`) resumen del cumplimiento del 30%.

---

## MÓDULO 6 — EQUIPOS Y EQUIPAMIENTO (o ESTÁNDARES MINEDUC si Conservación)

### 6.A Equipos y Equipamiento

Planilla editable de precios unitarios (`PRECIOS_UNITARIOS_DEFAULT`, por categoría: mobiliario salas, equipamiento sala cuna, cocina general, cocina sala cuna, administración, enfermería, aseo, material didáctico inicial), generación automática de cantidades desde el programa arquitectónico (`generarPlanillaEquipamiento`), edición en línea de precio/cantidad, subtotales por categoría + IVA. El total con IVA se suma a I₀ en el Módulo 7.

### 6.B Estándares MINEDUC (si Conservación)

Genera **Carta de Declaración de Cumplimiento de Estándares** (`generarCartaEstandares`) y **Declaración de No Fraccionamiento** (`generarDeclaracionNoFraccionamiento`) — documentos Word cortos con firma del director/a.

---

## MÓDULO 7 — EVALUACIÓN ECONÓMICA (VAC / CAE)

### 7.0 Nivel 0 / Exento (`nivel_proporcionalidad === 'exento'`)

No requiere evaluación económica ni indicadores de rentabilidad social (Instructivo de Proporcionalidad SNI, sección 3.1). En su lugar, genera **Estudio Preinversional Simplificado** (`generarEstudioPreinversionalSimplificado`) y **Declaración de No Fraccionamiento**, con checklist de antecedentes de respaldo requeridos (carta de la institución financiera, presupuesto detallado firmado, plan de contingencia valorizado si corresponde, diseño aprobado si aplica, EETT y TDR, certificado de dominio/BNUP) y su propia sección de Documentos Adjuntos.

### 7.1 Costos de Construcción por Materialidad — Presupuestos Tipo itemizados

`COSTOS_CONSTRUCCION` ya **no** es una tabla plana UF/m² — son **presupuestos itemizados reales** por materialidad, extraídos de proyectos JUNJI/SLEP reales, en 6 categorías estándar (obras preliminares, obra gruesa, terminaciones, equipamiento y mobiliario, instalaciones, obras complementarias), expresados en **UF/m² por categoría** (inflación-neutral):

```javascript
const COSTOS_CONSTRUCCION = {
  HA:       { nombre: 'Hormigón Armado',    grupo: 'pesado',  vu: 50, mant_prev: 0.001,  mant_corr: 0.012, fuente: '...', categorias: { obras_preliminares, obra_gruesa, terminaciones, equipamiento_mobiliario, instalaciones, obras_complementarias } },
  ALB:      { nombre: 'Albañilería Confinada', grupo: 'pesado', vu: 30, mant_prev: 0.0018, mant_corr: 0.015, fuente: '...', categorias: { /* ... */ } },
  METALCON: { nombre: 'Metalcón',           grupo: 'liviano', vu: 20, mant_prev: 0.0012, mant_corr: 0.013, fuente: '...', categorias: { /* ... */ } },
  SIP:      { nombre: 'Panel SIP',          grupo: 'liviano', vu: 20, mant_prev: 0.0015, mant_corr: 0.014, fuente: '...', categorias: { /* ... */ } }
};
const NOMBRES_GRUPOS_MATERIALIDAD = { pesado: 'sistemas tradicionales (Hormigón Armado / Albañilería)', liviano: 'sistemas livianos e industrializados (Metalcón / Panel SIP)' };
```

`ufM2TotalMaterialidad(materialidad)` suma las 6 categorías. `calcularCostosConstruccion(programa, materialidad)` multiplica cada categoría × superficie × `PRECIOS_SOCIALES_2026.VALOR_UF`, agrega gastos generales (20%), utilidades (15% sobre directo+GG), IVA, y consultoría (3.20 UF/m²).

**Comparabilidad por grupo**: HA y ALB (`grupo: 'pesado'`) son comparables entre sí; METALCON y SIP (`grupo: 'liviano'`) son comparables entre sí; **no** se debe comparar un grupo contra el otro (son soluciones constructivas demasiado distintas). `renderResultadosEvaluacion()` muestra una alerta explícita si las alternativas activas abarcan más de un grupo.

**Vidas útiles** (`vu`, años): HA 50, ALB 30, METALCON 20, SIP 20 — usadas en el cálculo de Valor Residual.

**Actualización a UF editable**: `PRECIOS_SOCIALES_2026.VALOR_UF` (pesos por UF) y `FECHA_VALOR_UF` son campos editables en Configuración → Parámetros, para reajustar el presupuesto completo a la fecha vigente sin tocar los UF/m² de cada partida (que son fijos, tomados de los presupuestos reales fuente).

**Desglose por categoría** (`renderDesgloseObrasCiviles`): dentro de cada alternativa, mostrar el detalle categoría por categoría en pesos, la fuente citada, y el Valor UF usado.

### 7.2 Costos de Operación y Mantención (`costos_om`) — situación Actual vs. Proyecto

Tabla: Personal | Material Didáctico | Gastos Administrativos (servicios básicos y aseo) — cada uno con columna Actual (editable) y Proyecto (editable), más Mantención Preventiva/Correctiva Actual (la mantención "con proyecto" se define por alternativa, según su materialidad).

**El incremental (`proyecto - actual`) es lo único que alimenta VAC/CAE** — nunca el monto total "con proyecto":
```javascript
function calcularCostoOMAnualIncremental(alternativa) {
  const om = APP_STATE.proyecto.costos_om;
  const incPersonal = (om.personal.proyecto||0) - (om.personal.actual||0);
  const incMaterial = (om.material_didactico.proyecto||0) - (om.material_didactico.actual||0);
  const incGastos   = (om.gastos_administrativos.proyecto||0) - (om.gastos_administrativos.actual||0);
  const incMantPrev = (alternativa.mant_prev_proyecto||0) - (om.mant_prev_actual||0);
  const incMantCorr = (alternativa.mant_corr_proyecto||0) - (om.mant_corr_actual||0);
  return incPersonal + incMaterial + incGastos + incMantPrev + incMantCorr;
}
```

**Tres escenarios que la fórmula anterior cubre correctamente si los inputs se llenan bien:**
1. **Establecimiento existe, el proyecto aumenta capacidad**: operación (personal, material didáctico, gastos administrativos) y mantención cambian ambos — actual = cifras reales, proyecto = nuevas cifras.
2. **Establecimiento existe, el proyecto NO aumenta capacidad** (reposición/conservación pura): operación queda igual (actual = proyecto, incremental 0); mantención sí cambia (infraestructura nueva es más eficiente de mantener, normalmente ahorro).
3. **Establecimiento nuevo** (`esConstruccionNueva()`): no hay situación actual real — se usan valores teóricos tanto para operación como para mantención (ver 7.3/7.4/7.5).

`sugerirMantencionAlternativa(alternativa)`: si el usuario no ha ingresado un valor propio, sugiere Mantención Preventiva/Correctiva "con proyecto" como `costo_directo × mat.mant_prev` / `mat.mant_corr` según la materialidad de esa alternativa (ver tabla de arriba).

### 7.3 Bloqueo automático de "situación actual" para Construcción nueva

Cuando `esConstruccionNueva()`, `renderCostosOM()` **fuerza a 0 y deshabilita** los siguientes campos, con la nota "No aplica — proyecto nuevo" en cada uno y un aviso general arriba de la tabla:
- `programa_arq.superficie_actual`
- `costos_om.personal.actual`, `.material_didactico.actual`, `.gastos_administrativos.actual`
- `costos_om.mant_prev_actual`, `.mant_corr_actual`

Al volver a cualquier otro `tipo_proceso`, estos campos se re-habilitan normalmente (sin perder lo ya ingresado antes de haber sido "Construcción").

### 7.4 Referencias teóricas de Gastos Administrativos y Material Didáctico

Extraídas de un EPI real ("JI Las Cuncunitas", SLEP del Aconcagua): situación actual 313 m² → $7.709.288/año de Gastos Administrativos (**$24.630/m²/año**); 84 cupos actuales → $30.000.000/año de Material Didáctico (**$357.143/cupo/año**). Sirven de base de cálculo cuando no hay situación actual real (Construcción nueva).

```javascript
const REFERENCIA_GASTOS_ADMIN_M2 = 24630;
const REFERENCIA_MATERIAL_DIDACTICO_CUPO = 357143;

function sugerirGastosAdministrativosProyecto() {
  const superficieActual = p.programa_arq.superficie_actual || 0;
  const superficieProyecto = p.programa_arq.superficie_total || 0;
  if (superficieActual > 0) return Math.round((p.costos_om.gastos_administrativos.actual||0) * (superficieProyecto / superficieActual));
  return Math.round(REFERENCIA_GASTOS_ADMIN_M2 * superficieProyecto); // escala por SUPERFICIE (servicios básicos: electricidad, agua, gas + aseo)
}

function sugerirMaterialDidacticoProyecto() {
  const cuposActual = calcularCuposActualesTotal(); // suma de icov.niveles activos (SC+NM)
  const cuposProyecto = (p.programa_arq.cupos_sc||0) + (p.programa_arq.cupos_nm||0);
  if (cuposActual > 0) return Math.round((p.costos_om.material_didactico.actual||0) * (cuposProyecto / cuposActual));
  return Math.round(REFERENCIA_MATERIAL_DIDACTICO_CUPO * cuposProyecto); // escala por CAPACIDAD
}
```

Cada fila de Material Didáctico y Gastos Administrativos muestra el valor "Sugerido" con un botón "usar" que aplica el cálculo al campo "Situación con Proyecto" (`btn-usar-sugerido`, no automático — el usuario decide cuándo aplicarlo). Nota fija bajo la tabla citando la fuente y aclarando que es un valor de referencia editable.

### 7.5 Dotación Teórica según Decreto N°181 (2005, MINEDUC)

Coeficientes de dotación mínima por razón niño/adulto (Decreto 181, que modifica el Decreto 177/1996):

| Cargo | Razón |
|---|---|
| Director(a)/Coordinador(a) | 1 fijo por establecimiento |
| Educadora Sala Cuna | 1 cada 40 lactantes |
| Técnico Sala Cuna | 1 cada 6 lactantes |
| Manipuladora de Alimentos Sala Cuna | 1 cada 40 lactantes |
| Educadora Nivel Medio | 1 cada 48 niños |
| Técnico Nivel Medio Menor | 1 cada 12 niños |
| Técnico Nivel Medio Mayor | 1 cada 16 niños |
| Manipuladora de Alimentos Niveles Medios | 1 cada 70 niños |
| Auxiliar de Servicios Menores | 1 cada 100 niños (todo el establecimiento) |

```javascript
const DOTACION_DTO181 = [
  { id: 'director', nombre: '...', calc: (sc, nm) => (sc+nm) > 0 ? 1 : 0 },
  { id: 'educadora_sc', nombre: '...', calc: (sc) => Math.ceil(sc / 40) },
  { id: 'tecnico_sc', nombre: '...', calc: (sc) => Math.ceil(sc / 6) },
  { id: 'manipuladora_sc', nombre: '...', calc: (sc) => Math.ceil(sc / 40) },
  { id: 'educadora_nm', nombre: '...', calc: (sc, nm) => Math.ceil(nm / 48) },
  { id: 'tecnico_nmm', nombre: '...', calc: (sc, nm) => Math.ceil((nm/2) / 12) },
  { id: 'tecnico_nmmy', nombre: '...', calc: (sc, nm) => Math.ceil((nm/2) / 16) },
  { id: 'manipuladora_nm', nombre: '...', calc: (sc, nm) => Math.ceil(nm / 70) },
  { id: 'auxiliar', nombre: '...', calc: (sc, nm) => Math.ceil((sc+nm) / 100) }
];

function obtenerCuposActualesPorNivel() {
  if (esConstruccionNueva()) return { sc: 0, nm: 0 }; // no existe situación actual
  const niveles = p.diagnostico.icov.niveles || {};
  const get = cod => (niveles[cod]?.activo) ? (niveles[cod].O || 0) : 0;
  return { sc: get('SCM') + get('SCMy'), nm: get('NMM') + get('NMMy') };
}
```

**Escala Única de Sueldos (EUS)** — `ESCALA_REMUNERACIONES_EUS_2025`: remuneraciones brutas mensuales año 2025 (fuente: planilla oficial de grados/remuneraciones del sector público, columna "Remuneración Bruta Mensual con Asig. de Modernización"), llevadas a **UF** con la UF del 31-12-2024 ($38.416,69), agrupadas por categoría (`DIR / C.T.`, `PROF / C.T.`, `TEC.ADM.AUX / C.T.`, `TEC / S.T.`, `ADM / S.T.`, `AUX / S.T.` — C.T.=Con Título, S.T.=Sin Título) y grado.

```javascript
function sueldoAnualDesdeGrado(categoria, grado, valorUf) {
  const fila = ESCALA_REMUNERACIONES_EUS_2025.find(f => f.categoria === categoria && f.grado === grado);
  return fila ? Math.round(fila.uf_mensual * 12 * (valorUf || 0)) : 0;
}
```

**Calculadora en Módulo 7, dentro de Costos de Operación** (`renderCalculadoraDotacionDTO181`, contenedor `#calc-dotacion-dto181-m7`):
- Input **"Valor UF para sueldos"** (editable, default $39.727,96 = UF del 31-12-2025) + fecha de esa UF. Nota fija: **"Usa siempre la UF del 31 de diciembre del año anterior para calcular los sueldos teóricos del año en curso"** (ej.: en 2026 se usa la UF del 31-12-2025).
- Por cada cargo del Decreto 181 visible (dotación actual o proyectada > 0): dotación actual (calculada, no editable), dotación proyectada (calculada), un `<select>` con optgroups por categoría EUS que autocompleta el costo anual por persona al elegir un grado, y el campo de costo **siempre editable manualmente** (si se elige "— Ingresar manualmente —" o se escribe directo, no se pisa).
- Al cambiar el Valor UF, **recalcular automáticamente** solo los costos derivados de un grado seleccionado (los tipeados a mano quedan intactos).
- Botón **"Aplicar dotación teórica a Personal (O&M) y al Modelo de Gestión"** (confirmación de doble clic si la tabla de dotación del Módulo 9 ya tiene filas): calcula el total (Σ dotación × costo por persona) para actual y proyectada, lo escribe en `costos_om.personal.actual/.proyecto` (alimenta el CAE), y guarda el detalle itemizado en `proyecto.modelo_gestion.dotacion` (alimenta el Módulo 9). **La tabla de dotación es la fuente de la cifra agregada de Personal** — igual que en un CCOM real, donde el total de la tabla de dotación coincide exactamente con la línea "Personal" del cuadro de costos de operación.

---

## MÓDULO 8 — REDACCIÓN ASISTIDA POR IA

### 8 secciones (orden fijo, basado en la estructura real de un EPI JUNJI aprobado)

```javascript
const SECCIONES_REDACCION = {
  introduccion:            { titulo: '1. Introducción y Resumen Ejecutivo', prompt_template: (data) => `...` },
  area_estudio:            { titulo: '2. Área de Estudio', prompt_template: (data) => `...` },       // con apoyo visual
  establecimiento_foco:    { titulo: '3. Establecimiento Foco del Estudio', prompt_template: (data) => `...` },
  area_influencia:         { titulo: '4. Área de Influencia', prompt_template: (data) => `...` },     // con apoyo visual
  diagnostico:             { titulo: '5. Diagnóstico', prompt_template: (data) => `...` },
  alternativas:            { titulo: '6. Análisis de Alternativas', prompt_template: (data) => `...` },
  evaluacion_economica:    { titulo: '7. Evaluación Económica', prompt_template: (data) => `...` },
  conclusion:              { titulo: '8. Conclusión y Recomendación', prompt_template: (data) => `...` }
};
const SECCIONES_CON_APOYO_VISUAL = new Set(['area_estudio', 'area_influencia']);
```

Cada sección: textarea editable, botones "Generar con IA" / "Mejorar redacción", indicador de tokens usados (`actualizarTokensUsados`). `area_estudio` y `area_influencia` tienen además una **tabla editable de indicadores** (`{ etiqueta, valor, fuente }`) y una galería de imágenes/mapas, cuyo contenido se inyecta en el prompt vía `construirContextoProyecto()`.

Cada `prompt_template` debe embeber un **extracto real de referencia** (de otro proyecto EPI JUNJI ya redactado y aprobado), etiquetado explícitamente como "Ejemplo real de referencia (de OTRO proyecto — usa su estructura y nivel de precisión como modelo, NUNCA copies sus datos)" — para calibrar el estilo institucional sin inventar cifras ni copiar datos de un proyecto ajeno al que se está formulando.

### Anti-Markdown (aplicar SIEMPRE en toda generación de texto con IA, en Módulo 8 y 9)

```javascript
const INSTRUCCION_SIN_MARKDOWN = '\n\nIMPORTANTE: Responde en texto plano, sin formato Markdown (nada de #, ##, **, __, guiones ni números para listas). Escribe solo párrafos de prosa corrida, tal como se vería ya impreso en un documento Word.';

function limpiarMarkdown(texto) {
  return (texto || '')
    .replace(/^#{1,6}\s+/gm, '')
    .replace(/\*\*(.*?)\*\*/g, '$1')
    .replace(/__(.*?)__/g, '$1')
    .replace(/\*([^*\n]+)\*/g, '$1')
    .replace(/^[-*]\s+/gm, '')
    .replace(/^\d+\.\s+/gm, '')
    .trim();
}
```

Todo prompt enviado a Claude concatena `INSTRUCCION_SIN_MARKDOWN` al final; toda respuesta pasa por `limpiarMarkdown()` antes de guardarse/mostrarse — doble resguardo (instrucción + regex de limpieza), porque el modelo a veces igual devuelve Markdown pese a la instrucción.

**Llamada a Claude (siempre vía el proxy local, nunca directo a `api.anthropic.com`):**
```javascript
const CLAUDE_API_URL = 'http://localhost:8787/v1/messages';
async function generarTextoIA(seccion) {
  const prompt = SECCIONES_REDACCION[seccion].prompt_template(construirContextoProyecto()) + INSTRUCCION_SIN_MARKDOWN;
  const response = await fetch(CLAUDE_API_URL, {
    method: 'POST',
    headers: { 'x-api-key': APP_STATE.config.anthropic_api_key, 'anthropic-version': '2023-06-01', 'content-type': 'application/json' },
    body: JSON.stringify({ model: 'claude-opus-4-8', max_tokens: 1024, messages: [{ role: 'user', content: prompt }] })
  });
  const result = await response.json();
  const texto = limpiarMarkdown(result.content[0].text);
  // guardar en proyecto.redaccion[seccion], actualizar textarea, actualizarTokensUsados(seccion, result.usage)
}
```
`mejorarRedaccion(seccion)` sigue el mismo patrón, pidiendo pulir estilo/claridad manteniendo cifras y contenido del texto ya escrito.

---

## MÓDULO 9 — RESUMEN, MODELO DE GESTIÓN Y EXPORTACIÓN

### 9.1 Ficha Resumen

Identificación, diagnóstico ICov/ICal/INS, solución recomendada, comparación de alternativas + botones Exportar JSON / Copiar resumen / Imprimir.

### 9.2 Modelo de Gestión — siempre visible, sin toggle

Sección nueva, **siempre disponible** (no depende del nivel de proporcionalidad ni de la etapa — la metodología SNI lo exige para todo proyecto, y va al final porque debe usar los datos ya elaborados en los módulos anteriores, no recalcularlos por su cuenta). Estructura basada en un Modelo de Gestión real (presentado en respuesta a una observación de RATE).

**7 ejes**, cada uno con textarea + "Generar con IA"/"Mejorar redacción" (mismo patrón que Módulo 8), y 3 tablas editables intercaladas junto al eje que corresponde:

```javascript
const EJES_MODELO_GESTION = {
  institucional: { titulo: '1. Eje Institucional y de Gobernanza', prompt_template: (data) => `...` },
  rrhh:          { titulo: '2. Eje de Dotación y Recursos Humanos', prompt_template: (data) => {
    // incluye en el prompt las filas ya cargadas en proyecto.modelo_gestion.dotacion (cargo, actual→proyectada), NO inventa cifras
  }},
  materiales:    { titulo: '3. Eje de Recursos Materiales y Equipamiento', prompt_template: (data) => {
    // incluye proyecto.equipamiento.total_con_iva si existe
  }},
  financiero:    { titulo: '4. Eje Financiero: Operación y Sostenibilidad Presupuestaria', prompt_template: (data) => {
    // lee EN VIVO proyecto.costos_om (personal+material+gastos, actual/proyecto) — no repite el cálculo, lo USA
  }},
  mantencion:    { titulo: '5. Eje de Mantención de la Infraestructura', prompt_template: (data) => {
    // lee EN VIVO costos_om.mant_prev_actual/mant_corr_actual + ganadora.mant_prev_proyecto/mant_corr_proyecto
  }},
  continuidad:   { titulo: '6. Eje de Continuidad Operacional durante la Ejecución de las Obras', prompt_template: (data) => {
    // incluye las filas ya cargadas en proyecto.modelo_gestion.cronograma, NO inventa hitos/plazos
  }},
  calidad:       { titulo: '7. Eje de Aseguramiento de la Calidad y Reconocimiento Oficial', prompt_template: (data) => `...` }
};
```

Cada `prompt_template` embebe también un extracto real de referencia del Modelo de Gestión fuente, con la misma salvaguarda "usa la estructura, nunca copies las cifras".

**Tabla de Dotación de Personal** (bajo el eje RRHH): `{ cargo, dotacion_actual, costo_actual_anual, dotacion_proyectada }`, agregar/editar/quitar fila libremente — se puebla automáticamente al usar la Calculadora de Dotación DTO-181 del Módulo 7 (ver 7.5), pero queda editable después para reflejar contrataciones reales por sobre el mínimo legal.

**Cronograma de Acciones e Hitos** (bajo el eje Continuidad): `{ hito, plazo }`.

**Gestión de Riesgos** (sección independiente, no atada a un eje): `{ riesgo, efecto, mitigacion }`.

**Generación del documento** (`generarModeloGestion()`, .docx): Portada → Introducción → Identificación del Proyecto (tabla auto-poblada desde el estado del proyecto) → Síntesis del Diagnóstico y la Evaluación (ICov/ICal/INS/CAE) → los 7 ejes en orden, con la tabla de Dotación insertada después del eje RRHH, la tabla de Costos de Operación después del eje Financiero, la tabla de Mantención después del eje Mantención, y el Cronograma después del eje Continuidad → Gestión de Riesgos → Conclusión → firma del director/a.

### 9.3 Exportación a PDF del EPI completo

Botón **"Generar EPI Completo (PDF)"** (junto a "Imprimir", en la barra de la Ficha Resumen). No usa ninguna librería de generación de PDF — arma una **vista de impresión dedicada** y delega en `window.print()` (el usuario elige "Guardar como PDF" en el diálogo nativo del navegador), el mismo mecanismo ya usado por "Imprimir", pero ensamblando el estudio completo en vez de solo la ficha.

- `<div id="vista-impresion-epi"></div>` como hermano de `#app` (fuera del árbol normal de pantallas), `display:none` salvo en modo impresión.
- CSS: `body.modo-impresion-epi #app { display:none }` / `body.modo-impresion-epi #vista-impresion-epi { display:block }`, con `.epi-seccion { page-break-before: always }` (excepto la primera) para que cada sección caiga en su propia página, y estilos propios de tabla/imagen para impresión (header azul institucional, imágenes limitadas a 300×220px).
- `construirVistaImpresionEPI()`: arma el HTML — portada (nombre, BIP, institución, región/provincia/comuna, tipo de proceso, fecha) → las 8 secciones de `SECCIONES_REDACCION` en orden (cada una con su tabla de indicadores y, si es `area_estudio`/`area_influencia`, un contenedor para la galería de imágenes) → tabla resumen ICov/ICal/INS (con el mismo tratamiento "No aplica" que Módulo 4 cuando `esConstruccionNueva()`) → tabla comparativa de alternativas (VAC/CAE) → tabla de Costos de Operación y Mantención → Ficha Resumen final.
- `insertarImagenesEnVistaImpresion()`: como las imágenes de apoyo de redacción viven en el backend (`documentos` filtrados por `categoria === 'imagen_' + seccion`, requieren `Authorization: Bearer`), se recorren con `apiFetch` y se insertan como `<img>` con `URL.createObjectURL(blob)` — si no hay `proyecto_id` (modo demo, sin backend) esta función no hace nada y las secciones quedan solo con texto, sin romper el flujo.
- `generarEPICompletoPDF()`: puebla `#vista-impresion-epi`, espera las imágenes, agrega la clase `modo-impresion-epi` al `<body>`, llama `window.print()` con un pequeño `setTimeout` (para que el navegador aplique el layout de impresión antes de abrir el diálogo), y quita la clase al recibir el evento `afterprint`.

### 9.4 Helpers de generación de documentos Word (reutilizados en TODOS los módulos que generan .docx)

```javascript
function docxTitulo(texto) { /* centrado, negrita, tamaño 26 */ }
function docxParrafo(texto, opts) { /* justificado (o centrado si opts.centrado), tamaño 22 por defecto */ }
function docxTablaSimple(encabezados, filas) { /* tabla con header azul institucional #003366, texto blanco */ }
function docxFirma(nombre, cargo, institucion) { /* 3 párrafos centrados: nombre, cargo, institución */ }
async function descargarDocumentoWord(doc, nombreArchivo) { /* docx.Packer.toBlob + <a download> + toast */ }
```

Todos los generadores de documentos (`generarCertificadoCCOM`, `generarCertificadoConservacion`, `generarMemoriaConservacion`, `generarCartaEstandares`, `generarDeclaracionNoFraccionamiento`, `generarEstudioPreinversionalSimplificado`, `generarModeloGestion`) se construyen con estos mismos helpers para mantener estilo consistente.

---

## DISEÑO Y UX

### Paleta de colores

```css
:root {
  --primary: #003366; --secondary: #FFB800;
  --success: #28a745; --warning: #ffc107; --danger: #dc3545;
  --light-bg: #f8f9fa; --border: #dee2e6; --text-dark: #212529; --text-muted: #6c757d;
}
```

### Layout principal

Header (logo + nombre proyecto + usuario + botones Mis Proyectos/Configuración/Cerrar sesión) + Sidebar stepper (240px) + contenido principal con navegación Anterior/Guardar/Siguiente por módulo.

### Componentes reutilizables

```javascript
function renderSemaforo(valor, umbrales = { rojo: 0.5, amarillo: 0.8 }) {
  if (valor == null || isNaN(valor)) return '<span class="badge bg-secondary badge-semaforo">N/D</span>';
  const color = valor < umbrales.rojo ? 'danger' : valor < umbrales.amarillo ? 'warning' : 'success';
  return `<span class="badge bg-${color} badge-semaforo">${(valor*100).toFixed(1)}%</span>`;
}
```

Sistema de toasts (esquina inferior derecha) para confirmar guardados, errores de API, resultados de acciones.

---

## DATOS HARDCODEADOS / EMBEBIDOS

- `COMUNAS_CHILE`: las 16 regiones con sus provincias y comunas.
- `PRECIOS_SOCIALES_2026`: `{ IVA: 0.19, MOC: 0.97, MOSC: 0.95, MONC: 0.91, ARANCEL: 0.0078, VALOR_UF, FECHA_VALOR_UF }` (VALOR_UF y FECHA_VALOR_UF editables en Configuración).
- `COSTOS_CONSTRUCCION`: presupuestos itemizados por materialidad (ver Módulo 7.1).
- `PLANILLA_ICAL`: checklist normativo completo (ver Módulo 4).
- `PRECIOS_UNITARIOS_DEFAULT`: precios de equipamiento por categoría (ver Módulo 6).
- `BD_JARDINES_COORDS` / `BD_OTROS_ESTABLECIMIENTOS`: coordenadas reales JUNJI/INTEGRA/Privados (ver Módulo 2).
- `DOTACION_DTO181` / `ESCALA_REMUNERACIONES_EUS_2025`: coeficientes del Decreto 181 y escala de sueldos (ver Módulo 7.5).
- `REFERENCIA_GASTOS_ADMIN_M2` / `REFERENCIA_MATERIAL_DIDACTICO_CUPO`: referencias teóricas de O&M (ver Módulo 7.4).
- `EJEMPLO_DEMO`: proyecto "JI Las Cuncunitas" completo, precargado con el botón **"Ingresar a Demo"** (pantalla de login) — usar valores internamente consistentes entre sí (`alternativa_ganadora` debe calzar exactamente con el `nombre` de una de las `alternativas[]`, para que el CAE por cupo no quede "N/D" en la ficha resumen).

### Branding — sin "EPI" en el nombre del sistema

El nombre visible del sistema es **"Sistema de Formulación"**, sin la sigla "EPI" (que solo se usa en prosa, para referirse al documento — "Estudio Preinversional (EPI)" — nunca como parte del nombre/marca de la aplicación). Aplica en: `<title>`, el logo del header del dashboard (`JUNJI | Sistema de Formulación`), el logo de la pantalla de login, el logo mini de "Mis Proyectos", el título "FICHA RESUMEN" (sin EPI) del Módulo 9, y los metadatos/pie de página de la planilla Excel exportada. El logo debe llevar `white-space: nowrap` (y `flex-shrink: 0` en el header del dashboard, que comparte fila con el nombre del proyecto) para que "JUNJI | Sistema de Formulación" nunca se corte en dos líneas.

### Modo demo — aviso visible dentro del dashboard

Al entrar por "Ingresar a Demo" (o al abrir el demo local desde "Mis Proyectos" sin guardarlo en el servidor), `APP_STATE.proyecto_id` queda en `null`. Mientras esa condición se cumpla, mostrar una nota pequeña justo debajo del nombre del proyecto en el header del dashboard (`#aviso-modo-demo`, oculta por defecto): *"Se están usando datos del proyecto para fines de demostración."* — se activa/oculta en `mostrarDashboard()` con `aviso-modo-demo.classList.toggle('d-none', APP_STATE.proyecto_id != null)`, así se oculta automáticamente al abrir un proyecto real guardado en el backend.

---

## VALIDACIONES Y LÓGICA DE NEGOCIO

1. `ICov_j`: si `D_j_min = 0`, asumir `ICov_j = 1`.
2. `ICal`: no aplica para `tipo_proceso === 'Construcción'` (ver Módulo 4) — no forzar su cálculo en ese caso.
3. `INS`: `= ICal × ICov` normalmente; `= ICov` si `esConstruccionNueva()`.
4. `CAE`: alertar si VAC es negativo.
5. Nombre del proyecto: validar formato PROCESO + OBJETO + LOCALIZACIÓN.
6. Alternativas: mínimo 2 para calcular VAC/CAE (excepto en modo Actualización de Diseño, que usa 1 sola).
7. **Comparabilidad de materialidad**: alertar si las alternativas activas mezclan grupo `pesado` y `liviano`.
8. Costos de Operación y Mantención: alimentar VAC/CAE siempre con el **incremental**, nunca el monto total "con proyecto".
9. Construcción nueva: bloquear en 0 los campos "situación actual" de superficie, dotación y costos O&M; usar referencias teóricas (Decreto 181, $/m², $/cupo).
10. Claude API: si no hay API key configurada, deshabilitar botones de IA con mensaje explicativo, y mostrar el mismo aviso en Módulo 8 y Módulo 9.
11. Documentos adjuntos (Conservación/Exento): deshabilitar la sección con aviso si el proyecto no está guardado en el backend (modo demo sin cuenta).

---

## CRITERIOS DE CALIDAD OBLIGATORIOS

- [ ] Todos los cálculos (ICov, ICal, INS, VAC, CAE, Dotación DTO-181, Gastos Administrativos/Material Didáctico teóricos) producen resultados correctos con los datos de Las Cuncunitas.
- [ ] El mapa Leaflet carga, geocodifica, y ubica vecinos usando `BD_JARDINES_COORDS`/`BD_OTROS_ESTABLECIMIENTOS` antes de recurrir a Nominatim.
- [ ] La integración con Claude API funciona vía `proxy_claude.py`, y ningún texto generado deja rastros de Markdown (`#`, `**`, `-`) en el textarea ni en el .docx exportado.
- [ ] Con `backend_epi.py` corriendo: registro, login, `GET /api/me`, múltiples proyectos por cuenta, aislamiento entre cuentas, subida/descarga/eliminación de documentos adjuntos.
- [ ] El modo demo/invitado sigue funcionando sin `backend_epi.py`, persistiendo en `localStorage`.
- [ ] Cambiar `tipo_proceso` a "Construcción" oculta el checklist de ICal, ajusta el INS a `=ICov`, y bloquea en 0 los campos "situación actual" del Módulo 7 — y todo se revierte correctamente al volver a "Reposición" u otra tipología.
- [ ] La Calculadora de Dotación DTO-181 con cupos 40 SC + 56 NM reproduce exactamente los 9 cargos y sus cantidades (Educadora SC: 1, Técnico SC: 7, Educadora NM: 2, Técnico NMM: 3, Técnico NMMy: 2, etc.), y "Aplicar" sincroniza `costos_om.personal` con la tabla de Dotación del Módulo 9.
- [ ] Los presupuestos de materialidad (HA/ALB/METALCON/SIP) se reajustan correctamente al cambiar el Valor UF, y la alerta de comparabilidad de grupo aparece cuando corresponde.
- [ ] El Modelo de Gestión se genera siempre (sin toggle), usa en vivo los datos de `costos_om` y las tablas de Dotación/Cronograma ya cargadas, y el total de la tabla de Dotación coincide con la línea "Personal" de Costos de Operación en el documento exportado.
- [ ] La exportación JSON, Excel (con fórmulas), todos los documentos Word (CCOM, Conservación, Modelo de Gestión, etc.) y el PDF del EPI completo (`generarEPICompletoPDF`) funcionan sin errores de consola.
- [ ] El diseño es usable en desktop (1280px de ancho mínimo, óptimo desde 1440px para el layout de dos columnas del mapa).
