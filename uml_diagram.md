# PawPal+ UML Class Diagram (Final)

```mermaid
classDiagram
    class Priority {
        <<enumeration>>
        HIGH = 1
        MEDIUM = 2
        LOW = 3
    }

    class Task {
        +String name
        +int duration
        +Priority priority
        +String category
        +String pet_name
        +bool completed
        +Optional~int~ scheduled_time
        +Optional~String~ recurrence
        +Optional~date~ due_date
        +mark_complete() Optional~Task~
        +edit(name, duration, priority, category)
        +end_time() Optional~int~
        +is_recurring() bool
    }

    class Pet {
        +String name
        +String species
        +String breed
        +int age
        +List~Task~ tasks
        +add_task(task: Task)
        +remove_task(task: Task)
        +complete_task(task: Task) Optional~Task~
        +get_tasks() List~Task~
    }

    class Owner {
        +String name
        +int available_time
        +List~Pet~ pets
        +add_pet(pet: Pet)
        +remove_pet(pet: Pet)
        +get_all_tasks() List~Task~
        +get_tasks_by_pet(pet_name: String) List~Task~
        +get_tasks_by_status(completed: bool) List~Task~
    }

    class Scheduler {
        +Owner owner
        +List~String~ conflicts
        +generate_plan() List~Task~
        +get_explanation() String
        +sort_by_time(tasks: List~Task~) List~Task~
        +filter_tasks(pet_name, completed) List~Task~
        -_collect_eligible_tasks() List~Task~
        -_detect_conflicts(plan: List~Task~) List~String~
        -_fmt_time(minutes: int)$ String
    }

    Task --> Priority : uses
    Owner "1" --> "*" Pet : owns
    Pet "1" --> "*" Task : has
    Scheduler "1" --> "1" Owner : schedules for
    Task ..> Task : mark_complete() creates next
```
