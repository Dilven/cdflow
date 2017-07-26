---
title: all.json
menu: reference
weight: 1
---

# all.json Reference

These are the list of properties you can have in the config file `all.json` which should exist in the `config/` directory of your project.


| Key | Default | Required | Description | Example |
| --- | ------- | -------- | ----------- | ------- |
| `dns_domain` | - | yes | The domain of your service| `mergermarket.it` |
| `cpu` | - | yes | Amount of cpu allocated to your service | `16` |
| `memory` | - | yes | Amount of memory allocated to your service | `128` |
| `port` | - | yes | The port your service exposes inside the container| `8000` |
| `alb_listener_rule_priority` | - | yes | The priority for the service. A ALB listener can't have multiple services with the same priority. | `100` |
| `common_application_environment` | - | yes (can be empty) | Environment variables you want exposed to your service regardless of the environment it is running in | `{ "VERSION" : "123" }` |

## Quick Example

```json
    {
        "dns_domain": "example.com",
        "cpu": 16,
        "memory": 128,
        "port": 8000,
        "alb_listener_rule_priority": 100,
        "common_application_environment": {
            "ENV_VAR": "value"
        }
    }
```