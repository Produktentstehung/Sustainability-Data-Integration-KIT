# Odoo: what has to be set up, and why

Everything described here is created by `setup-odoo.ps1`. The script is
repeatable — existing records are updated rather than duplicated — so it can be
run against a fresh instance as well as against an existing one.

```powershell
powershell -ExecutionPolicy Bypass -File setup-odoo.ps1
```

It asks for the API key once and passes it on as an environment variable only.
The key is neither stored nor written to the log.

This page exists because a trial database expires and the next one has to be
rebuilt quickly. Nothing below was done by hand in the Odoo interface.

## 1. Connection

Set in `.env` (see `.env.example`):

| Variable | Meaning |
|---|---|
| `SDI_ODOO_URL` | address of the instance |
| `SDI_ODOO_DB` | database name, usually the same as the subdomain |
| `SDI_ODOO_USER` | login of a user with access to manufacturing |
| `SDI_ODOO_APIKEY` | leave empty in the file; the scripts ask for it |

A new trial gets a new URL and database name. Those two lines are the only
ones that have to change.

## 2. Custom fields on `product.template`

The life cycle assessment needs to know, per article, which flow and which
process in openLCA it belongs to. Odoo has no field for that, so the script
creates five:

| Field | Content |
|---|---|
| `x_studio_lca_flow_uuid` | flow in openLCA |
| `x_lca_material` | material as used in the assessment |
| `x_lca_process_id` | process in openLCA |
| `x_lca_parameter` | the parameter that carries the quantity |
| `x_lca_zero_parameters` | parameters to be set to zero for this variant |

If the account has no Odoo Studio, creating fields through the API fails. The
script says so and continues; the fields then have to be created by hand, as
type text.

## 3. Weights with more than two decimal places

Odoo rounds weights to two decimals by default. A part weighing three grams
becomes `0.00`, and every assessment built on it is wrong. The script raises
the precision of the *Stock Weight* unit.

This one is easy to miss: nothing fails, the numbers just turn to zero.

## 4. Products, bill of material, manufacturing order

Taken from the PLM export in `docs/sample_data/BOM_TRACEpen.csv`: seven
articles with weight and material, one bill of material with six positions and
one manufacturing order over 25 pieces.

The article number from the PLM becomes the *internal reference* in Odoo
(`default_code`), for example `000114` for the pen. That reference is the link
between PLM, ERP and the administration shell — and it is what the nameplate
carries as `OrderCodeOfManufacturer`.

## 5. Serial numbers

Only what is produced in house carries a serial number. Purchased parts do not:
a serial number on them would claim a production that never happened here.

Which articles those are is configured, not guessed — the PLM category marks
only one of the three purchased parts as such:

```
SDI_SERIAL_ARTICLES=000114,000116,000117,000120
SDI_ASSEMBLY_ARTICLE=000114
SDI_SERIAL_DIGITS=3
```

### The coding

```
000114-001-000116-038
   |     |     |     |
   |     |     |     +--  instance of the part: the 38th bolt produced
   |     |     +--------  article number of the part, from the PLM
   |     +--------------  instance of the assembly: pen number one
   +--------------------  article number of the assembly, from the PLM

000114-001-000000-000     the pen itself; it sits in nothing
```

The part instance counts the pieces actually produced of that kind. That is
what makes a machine measurement usable in a product pass: the energy belongs
to one piece, not to a type.

### How Odoo produces it

Odoo builds a serial number from three parts: a prefix, a running number and a
suffix. The script sets

| Article | Prefix | Digits | Suffix | Result |
|---|---|---|---|---|
| `000114` assembly | `000114-` | 3 | `-000000-000` | `000114-001-000000-000` |
| `000116` part | `000000-000-000116-` | 3 | — | `000000-000-000116-001` |

The leading zeros on a part are deliberate. While a bolt is being milled, no
one knows which pen it will end up in — assembly happens later. Those blocks
are filled in when the part is booked into an assembly order.

Because Odoo composes the number itself, a manufacturing order created by hand
in the interface gets a correct number too. That was the reason for doing it
this way rather than composing the number in a flow.

### After a restore or a rebuild

If serial numbers already exist, raise the counter of the number range above
them — otherwise Odoo hands out a number twice and the manufacturing order
fails only when someone books it. In Odoo: *Settings → Technical → Sequences*,
one range per article, field *Next Number*.

## 6. Booking an assembly

The link between a part and the pen it went into is a stock move on the
manufacturing order. `src/Assembly_Booking.json` creates it:

1. an order over one piece — a serial number describes one piece, not a batch
2. Odoo issues the serial number of the pen from the pattern above
3. every tracked component gets its own number, composed from the pen's
   instance and the component's own counter
4. the consumption is booked and the order closed
5. the result is written into the shell as `AssemblyRecords`

From then on the machine flow attaches its measurements to the serial numbers
of the booked assembly rather than to whatever was issued last.

Two things worth knowing. `button_mark_done` answers without an error even
when Odoo silently opened a dialog instead of closing the order, so the flow
reads the state back afterwards rather than trusting the answer. And the flow
reuses an open order instead of creating a new one on every run — otherwise a
few clicks leave a row of orders that never corresponded to a real pen.

If the records in the shell are ever lost, `src/Assembly_Backfill.json` reads
every completed order from Odoo and restores them. Odoo is the system of
record; the shell holds a copy.

## 7. Adapting the coding to your own products

The numbers above belong to the demonstrator. Three settings in `.env` change
them without touching any code:

```
SDI_ASSEMBLY_ARTICLE=000114        the article number of the assembly
SDI_SERIAL_ARTICLES=000114,...     which articles carry a serial number
SDI_SERIAL_DIGITS=3                digits of the running instance
```

Three digits allow 999 pieces per article. For a real series that is too few;
raising it is a one-line change here and in the number ranges Odoo keeps per
article.

The structure itself — assembly, instance, part, instance — is a decision of
this KIT, not a standard. Anyone who needs a different one changes the prefix
and suffix of the number ranges; Odoo composes the number, so nothing in the
flows has to be touched.
