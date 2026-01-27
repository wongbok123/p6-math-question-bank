# Heuristics Glossary

Problem-solving strategies (heuristics) used in Singapore Primary Mathematics.
These are the methods students use to solve word problems, not the topics themselves.

A question can have **0-3 heuristics**. Simple P1A MCQs and straightforward computation questions typically have **none**. P2 multi-step word problems often use 1-2.

---

## Before-After

**What it is:** Comparing quantities before and after a change (someone gives away, receives, transfers, etc.) to find an unknown.

**When to tag:** The problem describes a situation that changes (e.g., "after giving 20 to...", "after selling...") and you need to track what happens.

**Example:**
> Ali had some marbles. After giving 15 to Ben, he had 3 times as many as Ben. If Ben had 25 marbles at first, how many did Ali have at first?
>
> **Before:** Ali = ?, Ben = 25
> **After:** Ali gives 15 to Ben. Ali = 3 x Ben's new amount.

### Sub-type: One Item Unchanged

In a before-after problem, the quantity of one item stays the same while others change. The unchanged item becomes the anchor for solving. In ratio problems, make the unchanged item's units equal in both the before and after ratios.

**Example (ratio):**
> The ratio of Ali's money to Ben's money was 5:4. After Ali spent $60, the ratio became 5:8. How much money did Ben have?
>
> Ben's money is unchanged. Before: A:B = 5:4. After: A:B = 5:8.
> Make Ben's units the same: Before = 5:4 = 10:8. After = 5:8.
> Ali's change: 10 units → 5 units = 5 units = $60. 1 unit = $12.
> Ben = 8 units = **$96**

**Example (non-ratio):**
> A shop had 120 apples and 80 oranges. After selling some apples, the number of apples became twice the number of oranges. How many apples were sold?
>
> Oranges unchanged = 80. After: apples = 2 × 80 = 160? That's more than 120, so re-read — apples became half of oranges: 80 ÷ 2 = 40. Sold = 120 − 40 = **80 apples**

### Sub-type: All Items Changed

All quantities in a before-after problem change by different amounts. You cannot hold anything constant, so you must set up a working table tracking each quantity's before and after values to find new relationships.

**Example:**
> Ali, Ben, and Charlie had money in the ratio 8:3:1. After Ali gave $200 to Ben and Ben gave $150 to Charlie, all three had equal amounts. How much did they have altogether?
>
> Before: 8u, 3u, 1u. After: 8u−200, 3u+200−150 = 3u+50, 1u+150. All equal.
> 8u − 200 = 3u + 50 → 5u = 250 → u = 50. Total = 12u = 12 × 50 = **$600**

---

## Boomerang & Rugby

**What it is:** Composite area/perimeter technique specific to Singapore Math. A *boomerang* is the shape formed when a quadrant is removed from a square. A *half-rugby* (or *rugby ball*) is formed when a triangle is removed from a quadrant. These shapes recur frequently in P5-P6 area/perimeter questions.

**When to tag:** The figure involves quadrants cut from squares, or triangular regions removed from quadrants, forming curved crescent or boomerang shapes.

**Example:**
> The figure is made up of a square of side 14 cm and 4 quadrants. Find the shaded area.
>
> Identify each shaded region as a boomerang: Area of square - area of quadrant.
> Boomerang area = 14² - ¼π(14²) = 196 - 153.94 = **42.06 cm²**

---

## Branching

**What it is:** Processing a sequence of steps where each step operates on the result of the previous one. In P6 word problems this most commonly appears as the **Remainder Concept** — taking a fraction of a quantity, then a fraction of the remainder, and so on. Can also involve tree diagrams or systematic counting.

**When to tag:** The problem involves **multiple sequential steps** where each step depends on what remains from the previous one (e.g., "spent 1/3, then spent 1/4 of the remainder, then..."). Do **not** tag for a single operation like "Ali spent 1/3 of his money" — that is just a straightforward fraction calculation, not branching.

**Example:**
> A coin is tossed 3 times. How many possible outcomes are there?
>
> Branch: each toss has 2 outcomes. Total = 2 x 2 x 2 = **8**

### Sub-type: Remainder Concept

Problems where a fraction of a quantity is used, then a fraction of the *remainder* is used, and so on. Requires tracking what's left at each step — naturally forms a branching chain.

**Example:**
> Ali had $120. He spent 1/3 of it on a book. He then spent 1/4 of the remainder on food. How much did he have left?
>
> Spent on book: 1/3 x 120 = $40. Remainder = $80.
> Spent on food: 1/4 x 80 = $20. Left = **$60**

### Sub-type: Make a List / Table

Organising data into a structured list or table to find a pattern or ensure all cases are covered — a form of systematic enumeration.

**Example:**
> How many 3-digit numbers can be formed using the digits 1, 2, 3 without repetition?
>
> List: 123, 132, 213, 231, 312, 321 = **6 numbers**

---

## Constant Quantity

**What it is:** An invariant quantity persists through a change. Either the *difference* between two quantities stays the same, or their *total* stays the same. Recognising which quantity is constant unlocks the solution.

**When to tag:** The question involves a change where either the difference or the total between two quantities remains unchanged.

### Sub-type: Constant Difference

Two quantities change (e.g., both increase or decrease), but the *difference* between them stays the same. Applies to ages, transfers where both sides change equally, and geometry problems where overlapping areas maintain a constant difference.

**Example:**
> Ali is 8 years old. His father is 36 years old. In how many years will his father be 3 times Ali's age?
>
> Difference is always 36 - 8 = 28. When father = 3x Ali:
> 3x - x = 28, so x = 14. In 14 - 8 = **6 years**

### Sub-type: Constant Total

Two quantities change (one increases, the other decreases), but their *total* stays the same. Common in transfer problems.

**Example:**
> Ali has 50 stickers and Ben has 30. How many stickers must Ali give Ben so they have the same number?
>
> Total = 80 (constant). Equal = 40 each. Ali gives 50 - 40 = **10**

---

## Equal Portions

**What it is:** A fraction/percentage/decimal of one quantity equals a fraction/percentage/decimal of another. This generalises "Equal Fractions" to include percentages and decimals.

**When to tag:** Look for keywords like **"is the same as"** or **"is equal to"** connecting a fraction/percentage/decimal of one item to a fraction/percentage/decimal of another (e.g., "2/3 of Ali's money is the same as 3/4 of Ben's money", or "40% of X is equal to 25% of Y").

**Example:**
> 2/3 of Ali's money = 3/4 of Ben's money. Ali has $36. How much does Ben have?
>
> 2/3 x 36 = 24. So 3/4 of Ben's = 24. Ben's = 24 x 4/3 = **$32**

---

## Model Drawing

**What it is:** Drawing bar models (tape diagrams) to represent quantities visually. Bars represent unknowns and known values, making relationships visible.

**When to tag:** The question is best solved by drawing bars to compare or partition quantities.

**Example:**
> Ali has 3 times as many stickers as Ben. They have 120 stickers altogether. How many stickers does Ali have?
>
> **Bar model:**
> Ben: [====]
> Ali: [====][====][====]
> Total = 4 units = 120, so 1 unit = 30, Ali = 90

---

## Pattern Recognition

**What it is:** Identifying a repeating or growing pattern in numbers, shapes, or sequences, then extending it to find the answer. Common PSLE number pattern types include:
- Constant difference or consecutive numbers (e.g., +3, +3, +3)
- Square numbers (1, 4, 9, 16, 25, ...)
- Triangle numbers (1, 3, 6, 10, 15, ...)

**When to tag:** The question shows a sequence and asks for the nth term or a continuation.

**Example:**
> 2, 6, 12, 20, 30, ... What is the 8th number?
>
> Differences: 4, 6, 8, 10 (increasing by 2). Pattern: n(n+1).
> 8th number = 8 x 9 = **72**

---

## Quantity × Value

**What it is:** Items have different unit values — not necessarily monetary. The "value" can be price per item, legs per animal, wheels per vehicle, candies per child, etc. Use a structured table (quantity × unit value = total value) to organise the information.

**When to tag:** The question involves mixed items with different unit values and provides **one** total (either total quantity or total value). You use the table to compute the unknown total. If the question gives **both** totals and asks for the breakdown, that is a **Supposition** problem (which may also use a Quantity × Value table as its setup).

**Example:**
> Ali bought 3 pens at $5 each and 4 erasers at $2 each. How much did he spend altogether?
>
> | Item | Qty | Value each | Total |
> |------|-----|-----------|-------|
> | Pens | 3 | $5 | $15 |
> | Erasers | 4 | $2 | $8 |
> | **Total** | 7 | | **$23** |

**Example (non-monetary):**
> A farm has 5 cars and 8 motorcycles. How many wheels are there in total?
>
> | Vehicle | Qty | Wheels each | Total |
> |---------|-----|------------|-------|
> | Cars | 5 | 4 | 20 |
> | Motorcycles | 8 | 2 | 16 |
> | **Total** | 13 | | **36** |

---

## Repeated Items

**What it is:** A common item appears in two different ratios. To combine them, you must make the common item's units consistent across both ratios before solving.

**When to tag:** The question gives two separate ratios that share a common quantity (e.g., A:B = 2:3 and B:C = 4:5), and you need to find a combined ratio or total.

**Example:**
> In a bakery shop, there are curry, sardine, and kaya buns. There are 216 more curry than sardine buns. There are 3 times as many curry as kaya buns. There is 12% as many sardine buns as the total number of buns. How many buns are there?
>
> Sardine appears in two relationships. Express all quantities in consistent units of sardine buns, then use the difference (216) to find 1 unit.

---

## Simultaneous Concept

**What it is:** Two unknowns, two conditions. Solve by comparison (eliminate one unknown) or substitution.

**When to tag:** The question gives two separate relationships between two unknowns.

**Example:**
> 3 pens and 2 erasers cost $8. 1 pen and 2 erasers cost $4. Find the cost of 1 pen.
>
> (3P + 2E) - (1P + 2E) = 8 - 4
> 2P = 4, so 1 pen = **$2**

---

## Spatial Reasoning

**What it is:** Perceiving or manipulating shapes to solve geometry or area/perimeter problems. Includes identifying hidden shapes, rearranging parts of a figure, reasoning about folds, and handling overlapping regions.

**When to tag:** The question requires visual reasoning about shapes — folding, overlapping, rearranging, or spotting embedded shapes.

### Sub-type: Folded Shapes

Problems where paper or a shape is folded along a line, and students must find angles, lengths, or areas after the fold. Key insight: folding preserves lengths and creates equal angles.

**Example:**
> A rectangular piece of paper is folded along a diagonal. The overlapping region forms a triangle. Find angle x.
>
> Since folding preserves the angle, the folded angle = the original angle. Use angle sum of triangle = 180°.

### Sub-type: Gap & Overlap

When two or more regions overlap, the total area = sum of individual areas minus the overlap. When there's a gap, total = sum + gap. A counting principle applied to geometry.

**Example:**
> Two squares of side 10 cm overlap with a 3 cm × 3 cm shared region. Find the total area covered.
>
> Total = 10² + 10² - 3² = 100 + 100 - 9 = **191 cm²**

### Sub-type: Spotting Hidden Shapes

Identifying familiar shapes (triangles, rectangles, semicircles, etc.) that are hidden or embedded within a more complex figure. The question can't be solved until you "see" the hidden shape.

**Example:**
> In the figure, ABCD is a rectangle. E is the midpoint of BC. Find the shaded area.
>
> The shaded region is actually a triangle AED. Spot it, then use ½ × base × height.

### Sub-type: Visual Regrouping (Cut & Paste)

Rearranging parts of a figure — mentally or on paper — by cutting a piece from one position and pasting it elsewhere to form a simpler shape (usually a rectangle or square).

**Example:**
> Find the area of an L-shaped figure (8 cm × 10 cm with a 4 cm × 5 cm rectangle removed).
>
> Cut the protruding part and paste it into the gap to form a full rectangle, or split into two rectangles and add.

---

## Supposition

**What it is:** "Suppose all are X" — assume all items are one type, calculate the expected total, then compare with the actual total. The difference reveals how many are the other type. Covers systematic trial-and-error and excess/shortage scenarios.

**When to tag:** Classic chickens-and-rabbits style problems, any problem with two types and a combined total, or problems comparing two hypothetical distribution scenarios.

**Example:**
> There are 10 coins of 20-cent and 50-cent coins. The total value is $3.80. How many 50-cent coins?
>
> Suppose all are 20c: 10 x 20 = 200c ($2.00). Actual = 380c.
> Extra = 180c. Each swap (20c to 50c) adds 30c. So 180/30 = **6 fifty-cent coins**

### Sub-type: Guess & Check

Making a systematic guess, checking if it satisfies all conditions, then adjusting. Often organised in a table.

**Example:**
> A farmer has chickens and cows. There are 10 animals and 28 legs. How many chickens?
>
> Guess 5 chickens, 5 cows: 5(2) + 5(4) = 30 legs (too many)
> Guess 6 chickens, 4 cows: 6(2) + 4(4) = 28 legs. **6 chickens**

### Sub-type: Excess & Shortage

Comparing two different distribution scenarios — one results in excess (leftover), the other in shortage (not enough). The difference reveals the total.

**Example:**
> If each child gets 3 sweets, there are 2 left over. If each child gets 5 sweets, there are 6 short. How many children?
>
> Difference per child: 5 - 3 = 2. Difference in total: 2 + 6 = 8.
> Number of children = 8 / 2 = **4**

---

## Unitary Method

**What it is:** Assigning "units" or "parts" to unknown quantities, then solving by finding the value of 1 unit. Also covers proportional reasoning — finding a unit value and scaling up or down.

**When to tag:** The question involves unknown quantities that can be represented as units (e.g., "3 units = 120, so 1 unit = 40"), or direct/inverse proportion (scaling, more workers = less time).

**Example:**
> The ratio of boys to girls is 3 : 5. There are 40 students in total. How many boys are there?
>
> 3 units + 5 units = 8 units = 40
> 1 unit = 5, boys = 3 units = **15**

### Sub-type: Proportionality

Direct or inverse proportion. If one quantity doubles, the other doubles (direct) or halves (inverse).

**Example:**
> 4 workers can paint a wall in 6 hours. How long would 3 workers take?
>
> Inverse proportion: 4 x 6 = 24 worker-hours. 24 / 3 = **8 hours**

---

## Using Parallel Lines

**What it is:** Using properties of parallel lines — alternate angles, corresponding angles, co-interior angles, or extending lines — to connect disjointed parts of a figure and find unknown angles or lengths.

**When to tag:** The question involves parallel lines (explicitly stated or from rectangles/parallelograms) and requires angle reasoning across them.

**Example:**
> In the figure, AB is parallel to CD. Find angle x.
>
> Draw a line through the vertex parallel to AB and CD. Use alternate angles to split x into two parts that can each be found.

---

## Working Backwards

**What it is:** Starting from the end result and reversing each step to find the starting value. Undo operations in reverse order.

**When to tag:** The problem gives you the final amount and a sequence of operations, and asks for the starting value.

**Example:**
> A number is multiplied by 3, then 7 is subtracted, giving 20. What is the number?
>
> **Work backwards:** 20 + 7 = 27, then 27 / 3 = **9**
