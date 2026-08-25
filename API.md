# Inventory JSON API

The API is served under `/api` and uses the same Cloudflare Access protection as
the web interface. Interactive OpenAPI documentation is available at `/docs`.

## Resources

| Resource | List | Create | Get | Update |
|---|---|---|---|---|
| Bins | `GET /api/bins` | `POST /api/bins` | `GET /api/bins/{id}` | `PATCH /api/bins/{id}` |
| Bin items | `GET /api/items` | `POST /api/items` | `GET /api/items/{id}` | `PATCH /api/items/{id}` |
| Gear | `GET /api/gear` | `POST /api/gear` | `GET /api/gear/{id}` | `PATCH /api/gear/{id}` |
| Locations | `GET /api/locations` | `POST /api/locations` | `GET /api/locations/{id}` | `PATCH /api/locations/{id}` |

Creates return `201`; reads and updates return `200`. Unknown records and
foreign-key references return `404`. Invalid payloads and unknown gear
attribute keys return `422`.

API-created records store the authenticated Cloudflare Access email in
`created_by`. Service-token requests store the token's `common_name` identifier,
because those JWTs do not carry a human email. Existing records and records
created through the HTML interface retain a null value.

## Gear attributes

Gear requests use an `attributes` object keyed by the definitions for that item
type. A patch changes only the supplied keys. Setting an attribute to `null`
removes its stored value.

```json
{
  "name": "SG",
  "brand": "Gibson",
  "item_type_slug": "guitar",
  "attributes": {
    "setup_neck_relief": ".008 in",
    "setup_action_low_e": "4/64 in"
  }
}
```

The API intentionally has no delete endpoints. Destructive changes still
require the existing reviewed workflow.
