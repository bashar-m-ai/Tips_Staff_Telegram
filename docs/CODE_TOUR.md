# Code tour: how this project works, file by file

This is a reading guide. It does not change any code. Every code block below is copied from the real files, with an explanation next to it.

**Read the files in this order.** Each one builds on the one before.

| Step | File | Lines | What you learn |
|---|---|---|---|
| 1 | `staff.py` | 23 | Classes, objects, methods |
| 2 | `tip_pool.py` | 27 | Lists, loops, the actual maths |
| 3 | `web.py` | about 160 | Functions, checking input, errors, a tiny web server |
| 4 | `test_web.py` | about 110 | What a test is |
| 5 | `bot.py` | about 650 | A conversation as a set of states |
| 6 | `app.html` | about 1050 | HTML, CSS and JavaScript in one page |

A good way to learn: open the file on one side and this guide on the other, read one block, then explain it out loud in your own words before moving on.

---

## 1. `staff.py`: one person

```python
class StaffMember:
    def __init__(self, name, hours, department, multiplier):
        self.name = name
        self.hours = hours
        self.department = department
        self.multiplier = multiplier
        self.tips = 0
```

- A **class** is a template. `StaffMember` is the template for "one person who worked tonight".
- `__init__` runs once, when a new person is created. It is the setup step.
- `self` means "this particular person". `self.name = name` stores the name on that person so it can be read later.
- `multiplier` is `1.0` for a full share and `0.5` for a half share.
- `tips` starts at `0` because nobody has been paid yet. The split fills it in later.

Creating a person looks like this: `StaffMember("Anna", 8, "Kitchen", 1.0)`.

```python
    def weighted_hours(self):
        return self.hours * self.multiplier
```

- A **method** is a function that belongs to a class.
- This is where the half share happens. 4 hours at half share gives `4 * 0.5 = 2`, so that person counts as 2 hours.

```python
    def to_dict(self):
        return {
            "name": self.name,
            "dept": self.department,
            "hours": self.hours,
            "share": "full" if self.multiplier == 1.0 else "half",
            "tips": round(self.tips, 2),
        }
```

- A **dictionary** (`{...}`) is a set of labelled values. The web app needs the result in this shape so it can be sent over the internet as text.
- `"full" if ... else "half"` is a one-line choice: pick one of two values depending on a condition.
- `round(self.tips, 2)` rounds to 2 decimals, which means cents.

---

## 2. `tip_pool.py`: the whole pot

```python
class TipPool:
    def __init__(self, total_tips):
        self.total_tips = total_tips
        self.members = []

    def add_member(self, member):
        self.members.append(member)
```

- A `TipPool` holds the total and a **list** of people. `[]` is an empty list.
- `append` adds one item to the end of a list.

```python
    def split(self):
        kitchen_pool = self.total_tips / 2
        service_pool = self.total_tips / 2
```

- Step 1 of the rule: cut the pot in half. With €350, each side gets €175.

```python
        kitchen_wh = sum(m.weighted_hours() for m in self.members if m.department == "Kitchen")
        service_wh = sum(m.weighted_hours() for m in self.members if m.department == "Service")
```

- Step 2: add up the weighted hours for each team.
- Read the line from the right: "for every member `m`, **if** they are in the kitchen, take their weighted hours, then `sum` them all".
- This short form is called a **generator expression**. It is a loop written inside one line.

```python
        kitchen_rate = kitchen_pool / kitchen_wh
        service_rate = service_pool / service_wh
```

- Step 3: money per hour for each team. €175 ÷ 14 hours = €12.50 per hour.
- **A weak spot to notice:** if a team has nobody, `kitchen_wh` is `0`, and dividing by zero crashes the program. That is why the bot and the web app both refuse to calculate until each team has at least one person.

```python
        for member in self.members:
            if member.department == "Kitchen":
                member.tips = member.weighted_hours() * kitchen_rate
            else:
                member.tips = member.weighted_hours() * service_rate
```

- Step 4: a **for loop** goes through every person and writes their amount into `member.tips`.
- `if / else` picks which team's rate to use.

**Try it yourself.** Open a terminal in the project folder, type `python`, then:

```
from staff import StaffMember
from tip_pool import TipPool
pool = TipPool(350)
pool.add_member(StaffMember("Anna", 8, "Kitchen", 1.0))
pool.add_member(StaffMember("Ben", 7.5, "Service", 1.0))
pool.split()
pool.show()
```

Change the numbers and predict the result before you press Enter.

---

## 3. `web.py`: the small web server

This file does two jobs: it hands the page (`app.html`) to phones, and it answers calculation requests.

### Importing other files

```python
from staff import StaffMember
from tip_pool import TipPool
```

- `import` brings in code from another file. This is how the web app reuses the same maths as the bot instead of copying it.

### Checking a number

```python
def _positive_number(value, what, maximum):
    # bool is a kind of int in Python, so rule it out first
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise BadInput(f"{what} must be a number.")
    if not math.isfinite(value) or value <= 0:
        raise BadInput(f"{what} must be more than zero.")
    if value > maximum:
        raise BadInput(f"{what} is too high.")
    return float(value)
```

- **Never trust what comes from outside.** Anyone on the internet can send anything to this server, so every value is checked before it is used.
- `isinstance` asks "is this value of this type?".
- `raise` stops the function and reports a problem. `BadInput` is this project's own kind of error, defined a few lines above.
- `f"{what} must be a number."` is an **f-string**: the part in `{}` is replaced by the variable's value.
- `math.isfinite` rejects the odd values "infinity" and "not a number".

### Doing the calculation

```python
    pool.split()
    return {"total": round(total, 2), "people": [m.to_dict() for m in pool.members]}
```

- After all the checks pass, the server builds a `TipPool`, calls the same `split()` you read above, and returns the result as a dictionary.
- `[m.to_dict() for m in pool.members]` is a **list comprehension**: make a new list by doing something to every item.

### Answering a request

```python
        try:
            data = json.loads(self.rfile.read(length))
            result = calculate(data)
        except BadInput as problem:
            return self._send_json(400, {"error": str(problem)})
        except (ValueError, UnicodeDecodeError):
            return self._send_json(400, {"error": "Could not read the request."})
        self._send_json(200, result)
```

- `try / except` means "try this, and if it goes wrong, do that instead of crashing".
- **JSON** is the text format phones and servers use to send data. `json.loads` turns that text into a Python dictionary.
- `200` and `400` are **status codes**. 200 means "fine", 400 means "you sent something wrong".

### Running next to the bot

```python
def start_in_background(port=None):
    """Start the page without blocking, so the bot can keep running in the main thread."""
    server = make_server(port)
    threading.Thread(target=server.serve_forever, daemon=True, name="web").start()
    print(f"Web app running on port {server.server_address[1]}")
    return server
```

- A **thread** lets a program do two things at once. The bot runs in the main thread, and the web server runs in a second one.
- `daemon=True` means "stop this thread when the main program stops".

---

## 4. `test_web.py`: checking the code automatically

```python
def test_split_matches_the_bot(base_url):
    status, result = post(base_url, SHIFT)
    assert status == 200
    assert result["total"] == 350
    tips = {p["name"]: p["tips"] for p in result["people"]}
    assert tips == {"Anna": 100.0, "Cem": 75.0, "Ben": 175.0}
```

- A **test** is a small function that runs the real code and checks the answer.
- `assert` means "this must be true, otherwise the test fails".
- Tests are a safety net. After any change you run `python -m pytest -q`, and if something you broke is covered by a test, you find out in two seconds instead of at 23:00 in the restaurant.

---

## 5. `bot.py`: the Telegram conversation

The bot asks one question at a time. The key idea is a **state machine**: the bot is always in exactly one state, and each state only accepts certain answers.

```python
(
    MAIN_MENU, ASK_TOTAL, ASK_DEPT_ORDER, ASK_NAME, ASK_HOURS, ASK_SHARE,
    EDIT_MENU, EDIT_PERSON, EDIT_TOTAL, EDIT_NAME, EDIT_HOURS,
) = range(11)
```

- These are the states, as numbers 0 to 10 with readable names.
- The normal path is `MAIN_MENU → ASK_TOTAL → ASK_DEPT_ORDER → ASK_NAME → ASK_HOURS → ASK_SHARE`, then back to `ASK_NAME` for the next person.

### Turning typed text into a number

```python
def parse_positive(text):
    """Turn '7,5' or '7.5' into 7.5. Returns None if it is not a positive number."""
    try:
        value = float(text.replace(",", "."))
    except ValueError:
        return None
    if not math.isfinite(value) or value <= 0:
        return None
    return value
```

- People in Germany type `7,5`. Python only understands `7.5`, so the comma is replaced first.
- `float(...)` turns text into a number, and raises `ValueError` if the text is not a number, for example "abc".
- `None` means "nothing". The function returns it to say "this was not a usable number".

### One step of the conversation

```python
    total = parse_positive(update.message.text)
    if total is None:
        await update.message.reply_text(
            "⚠️ Enter a positive number, e.g. `350`",
            parse_mode="Markdown", reply_markup=reset_kb(),
        )
        return ASK_TOTAL
```

- `update` is the message that just arrived from Telegram.
- If the number is bad, the bot replies with a warning and **returns the same state**, so it asks again.
- `await` means "wait for this to finish". Sending a message goes over the internet and takes a moment, and `await` lets the bot serve other people in the meantime. Functions that use it start with `async def`.

### Remembering things between messages

Each person chatting with the bot gets their own storage box called `context.user_data`. The bot keeps the current `TipPool` in it, so two colleagues using the bot at the same time never mix up their numbers.

### Buttons

```python
def result_kb():
    # Shown under a finished split: fix a mistake or start a new one.
    return InlineKeyboardMarkup([
        [EDIT_BTN],
        [InlineKeyboardButton("💰 New Tip Split", callback_data="new_split")],
    ])
```

- A keyboard is a list of rows, and each row is a list of buttons.
- `callback_data` is a hidden label. When someone taps the button, Telegram sends that label back, and the bot uses it to decide what to do.

### Wiring it all together

Near the bottom, `register_handlers` contains a `ConversationHandler`. It is a big table that says: "in state X, if this kind of message or button arrives, run function Y". Reading that table is the fastest way to see the whole bot at once.

---

## 6. `app.html`: the web app

One file with three languages in it.

| Part | Language | Job |
|---|---|---|
| Inside `<style>` | CSS | How things look: colours, sizes, animations |
| Inside `<main>` | HTML | What is on the page: headings, buttons, inputs |
| Inside `<script>` | JavaScript | What happens when you tap something |

### Screens

```html
  <section id="home" class="screen active">
```

- Every screen is a `<section>`. All of them exist in the page at the same time, and only the one with the class `active` is shown.

```js
  function show(id) {
    document.querySelectorAll('.go').forEach(function (n) { n.classList.remove('go'); });
    document.querySelectorAll('.screen').forEach(function (s) { s.classList.toggle('active', s.id === id); });
    window.scrollTo(0, 0);
  }
```

- `show('people')` switches screens by moving the `active` class to the section with that id.
- `document.querySelectorAll('.screen')` means "find every element with the class `screen`".

### What the app remembers while you use it

```js
  var state = { total: null, people: [], editing: null, result: null, nextId: 1, splitId: null, viewing: false };
```

- One object holds everything about the split in progress. Screens read from it and buttons change it.

### Reacting to a tap

```js
  $('hours-minus').addEventListener('click', function () { replay($('hours-minus'), 'tap'); stepHours(-0.5); });
```

- `addEventListener('click', ...)` means "when this is tapped, run this function".
- `$('hours-minus')` is a short helper for "find the element with this id".

### Saving on the phone

```js
  function savedNames() {
    try { return JSON.parse(localStorage.getItem(NAMES_KEY)) || []; } catch (e) { return []; }
  }
```

- `localStorage` is a small storage box that every browser gives to each website. It stays on the phone.
- It can only store text, so lists are turned into JSON text when saving and back into a list when reading (`JSON.parse`).
- `|| []` means "if there is nothing saved yet, use an empty list".

### Asking the server to calculate

```js
    fetch('/api/split', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
```

- `fetch` sends a request to the server. This is the moment the shift leaves the phone, goes to `web.py`, runs through `tip_pool.py`, and comes back as a result.
- This one line is the bridge between the JavaScript in the browser and the Python on Railway.

### An animation

```css
@keyframes enter { from { opacity: 0; transform: translateY(8px); } to { opacity: 1; transform: none; } }
```

- `@keyframes` describes a movement: start invisible and 8 pixels lower, end fully visible in place. Each screen plays it when it appears.

---

## Ideas to practise on

Small changes you can try on your own computer. Run the tests after each one.

1. **Easiest:** add your own greeting to the `GREETINGS` list in `app.html`.
2. **Easy:** change the accent colour by editing `--purple` near the top of `app.html`.
3. **Medium:** write a new test in `test_web.py` for a shift with three kitchen people, working out the expected amounts by hand first.
4. **Harder:** the amounts are rounded one by one, so they can add up to one cent more or less than the total. Write a test that shows this, then think about how you would fix it in `tip_pool.py`.
