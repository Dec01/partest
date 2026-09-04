# Methodology cheatsheet (partest)

## Core 12 test cases

| Type | Question | H/V |
|------|----------|-----|
| request_default | Alive + form OK | H |
| request_compare_benchmark | Values match baseline | H |
| request_permissions | Role model in steady state | H |
| request_new_object | State right after create | V |
| request_update_object | State right after update | V |
| request_incorrect_body | Broken transport/structure | H |
| request_env_list | Admin vs public slices | H |
| request_params | Filter/sort/page | H |
| request_elements | Field at/over contract edge | H |
| request_not_found | Missing/deleted resource | H |
| request_extra_data | Mass-assign / ignore extra | H |
| request_not_allowed | Unsupported method | H |

## Subtype → P1 (summary)

| Subtype | P1 TC |
|---------|-------|
| GET STATIC | default, benchmark |
| GET DYNAMIC | default, permissions, not_found |
| GET LIST / BY PARENT / BY SELF | default, permissions (+ not_found for by-parent) |
| POST CREATE | default, permissions, new, incorrect_body, elements, extra |
| POST TO OBJECT | + permissions×2, parent not_found |
| PUT / PATCH | default, permissions, update, incorrect_body, elements, extra, not_found |
| DELETE * | default, permissions, not_found |
| ACTION | default, permissions, incorrect_body, elements, extra, not_found |

## Inference confidence

| Only when ≥0.99 may omit explicit type | Otherwise always pass type= |
|----------------------------------------|-----------------------------|
| 405 → not_allowed | permissions |
| 404 → not_found | new / update |
| broken raw content → incorrect_body | elements / extra / env / benchmark |

## Steps

1. StatusCode  
2–3. Form (swagger awareness + validate_model)  
4–5. Values (get element + benchmark/boundary)

## Generator (quick)

```bash
partest-gen from-openapi ./suite --file openapi.yaml --depth p1 --force --with-ui
partest-gen init-ui ./suite --force
python -m partest.ui.capture_baselines --scenes scenes.json --dry-run
```

Depth: `resources` → G2 · `default` → G3 · `p1` → G4.  
UI is separate (`init-ui` / `--with-ui`).  
After gen: see `post-gen-playbook.md` and `docs/PROJECT_GEN_ROADMAP.md`.
