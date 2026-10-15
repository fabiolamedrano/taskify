# Taskify

Gestor de tareas web responsivo para equipos: proyectos, tablero Kanban,
subtareas, comentarios, adjuntos, registro de tiempo y notificaciones.
Incluye API REST. Proyecto académico en desarrollo.

## Tecnologías
- Python y Django
- MySQL 8.4 (en Docker)
- Django REST Framework
- Tailwind CSS
- JavaScript y SortableJS

## Requisitos
- Python 3.12 o superior
- Docker Desktop
- Git

## Instalación

1. Clonar el repositorio:

```bat
git clone https://github.com/fabiolamedrano/taskify.git
cd taskify
```

2. Crear el entorno virtual e instalar dependencias:

```bat
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

3. Copiar `.env.example` a `.env` y completar los valores
   (contraseñas y `SECRET_KEY`). Para generar una clave:

```bat
python -c "import secrets; print(secrets.token_urlsafe(50))"
```

4. Levantar la base de datos (esperar unos 30 segundos la primera vez):

```bat
docker compose up -d
```

5. Crear las tablas, cargar datos de ejemplo y crear un superusuario:

```bat
python manage.py migrate
python manage.py seed_data
python manage.py createsuperuser
```

6. Iniciar el servidor:

```bat
python manage.py runserver
```

Abrir http://127.0.0.1:8000

## Usuarios de ejemplo
Contraseña de todos: `taskify123`

| Usuario | Rol |
|---|---|
| ana | Administrador |
| luis, maria, carlos | Miembro |
| cliente | Cliente (solo lectura) |

El panel de administración está en `/admin` (usar el superusuario creado).

## API REST
Disponible en `/api/` (requiere iniciar sesión). Recursos: users, teams,
team-members, projects, tags, tasks, subtasks, comments, attachments,
time-logs y notifications.

## Estilos
El CSS compilado (`static/css/output.css`) está incluido. Solo si se modifican
los estilos hay que volver a compilar con el ejecutable independiente de
Tailwind CSS:

```bat
.\tailwindcss.exe -i static/src/input.css -o static/css/output.css --watch
```

## Estado del proyecto
- [x] Modelos y panel de administración
- [x] Login, dashboard y proyectos
- [x] Tablero Kanban y detalle de tarea
- [ ] API REST
- [ ] Crear y editar desde la interfaz
- [ ] Equipos, notificaciones y roles