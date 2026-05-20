# MVP revisión académica de syllabus

Configura Ollama en `.env` con:

```bash
OLLAMA_BASE_URL=http://ollama:11434
LOCAL_LLM_MODEL=qwen2.5:7b
```

Si ejecutas el backend sin Docker, usa `OLLAMA_BASE_URL=http://localhost:11434`.
## Ejecutar

```bash
docker compose up
```

En una terminal separada, descarga el modelo dentro del contenedor de Ollama la primera vez:

```bash
docker compose exec ollama ollama pull qwen2.5:7b
docker compose exec ollama ollama list
```

Si `ollama list` no muestra `qwen2.5:7b`, el analisis fallara con `model not found`.

Servicios:

- Frontend: http://localhost:5173
- Backend API: http://localhost:8000/api/health
- PostgreSQL: localhost:5432

La primera ejecución construye las imágenes automáticamente. Si cambias dependencias, usa:

```bash
docker compose up --build
```

## Variables de entorno

Variables útiles:

- `DATABASE_URL`: conexión SQLAlchemy a PostgreSQL.
- `STORAGE_DIR`: carpeta interna donde se guardan PDFs.
- `ALLOWED_ORIGINS`: orígenes permitidos por CORS.
- `MAX_UPLOAD_MB`: tamaño máximo del ZIP.
- `AI_REQUEST_TIMEOUT_SECONDS`: timeout por llamada a IA. La IA solo compara JSON estructurados.
- `OLLAMA_BASE_URL`: URL del servidor local de Ollama.
- `LOCAL_LLM_MODEL`: modelo local a usar con Ollama.

Usa `.env.example` como referencia. El archivo `.env` local no se versiona.

## Probar el flujo completo

Genera un ZIP de ejemplo:

```bash
python3 samples/generate_sample_zip.py samples/syllabus_demo.zip
```

En Windows también puedes usar `python` si ese es el comando configurado.

Luego:

1. Abre http://localhost:5173.
2. Selecciona `samples/syllabus_demo.zip`.
3. Presiona `Subir ZIP`.
4. Selecciona el curso `2207`.
5. Presiona `Analizar`.

El ejemplo contiene tres NRC de Termodinámica. Dos tienen reglas equivalentes con distinta redacción y un tercero cambia ponderaciones y umbral de eximición. El análisis extrae datos estructurados desde los PDFs y luego usa la IA solo para comparar los JSON por NRC.

## Flujo de análisis

El backend guarda el PDF como respaldo y extrae por código los datos relevantes de cada syllabus. En concreto, prioriza:

- Información general de la asignatura.
- Evaluaciones y ponderaciones.
- Requisitos de aprobación.
- Nota final de la asignatura.
- Criterios de eximición y reglas especiales detectadas dentro de esas secciones.

Cada syllabus se transforma primero en un JSON estructurado con metadata, secciones, evidencia breve y advertencias. La IA recibe únicamente esos JSON por NRC y devuelve el reporte comparativo final.

## Formato esperado de archivos

Cada PDF dentro del ZIP debe llamarse:

```text
AÑOSEMESTRE-CARRERA-CODIGOCURSO-NRC-NUMERONRC-NOMBRERAMO.pdf
```

Ejemplo:

```text
202610-ING-2207-NRC-7542-TERMODINAMICA.pdf
```

El sistema extrae:

- Año: `2026`
- Semestre o periodo: `10`
- Carrera: `ING`
- Código del curso: `2207`
- NRC: `7542`
- Nombre del ramo: `TERMODINAMICA`

## Uso de la API

Subir ZIP:

```bash
curl -F "file=@samples/syllabus_demo.zip" http://localhost:8000/api/uploads/zip
```

Listar cursos agrupados:

```bash
curl http://localhost:8000/api/courses
```

Ejecutar análisis de un curso:

```bash
curl -X POST http://localhost:8000/api/courses/1/analyze
```

Consultar último reporte:

```bash
curl http://localhost:8000/api/courses/1/report/latest
```

## Qué guarda la base de datos

- `course_groups`: grupo por año-semestre y código de curso.
- `syllabi`: metadata extraída, ruta del PDF y texto extraído.
- `analysis_reports`: reporte comparativo por curso.
- `inconsistencies`: alertas por apartado, variable, NRC, gravedad y sugerencia.

## Alcance del análisis

El MVP analiza estos apartados:

- Evaluaciones y Ponderaciones.
- Requisitos de Aprobación.
- Criterios de Eximición.
- Nota Final de la Asignatura.

Variables intentadas:

- Número y tipo de evaluaciones.
- Ponderaciones porcentuales.
- Existencia de examen.
- Requisitos y nota mínima para rendir examen.
- Criterios mínimos de aprobación.
- Condiciones y umbral de eximición.
- Fórmula de cálculo de nota final.

El análisis se ejecuta en dos etapas:

1. El backend extrae por código un JSON estructurado para cada syllabus/NRC.
2. La IA compara esos JSON entre NRC y genera el reporte.

Con dos syllabus, el sistema solo reporta diferencias entre ambos. Con tres o más, intenta detectar el patrón mayoritario y marcar el NRC que más se aleja del grupo.

## Limitaciones del MVP

- No aprueba ni rechaza syllabus.
- No modifica documentos.
- No evalúa calidad pedagógica.
- No analiza bibliografía ni cronograma completo.
- No integra Canvas ni otros sistemas institucionales.
- No incluye OCR; PDFs escaneados o imagen pueden quedar sin texto.
- El análisis depende de la disponibilidad y rendimiento del servidor local de Ollama.
- La comparación depende de la calidad del JSON extraído por código.
- No hay autenticación ni roles de usuario.
