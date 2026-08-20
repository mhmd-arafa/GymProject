"""Seed the food database, with Egyptian staples first.

Per-100g macros so any gram amount computes. Values are typical cooked/ready-to-eat
figures for the Egyptian versions of these dishes -- foul made with oil, koshari as
sold in a street shop -- because that is what clients actually eat. The trainer can
correct any row in the admin.
"""

from django.db import migrations

# (name, category, kcal, protein, carbs, fat, is_egyptian_staple)
FOODS = [
    # --- Egyptian staples -------------------------------------------------
    ("Foul Medames", "COMPOSITE", 165, 8.0, 20.0, 5.5, True),
    ("Taameya (Egyptian Falafel)", "COMPOSITE", 330, 13.0, 32.0, 17.0, True),
    ("Koshari", "COMPOSITE", 185, 6.0, 33.0, 3.5, True),
    ("Baladi Bread", "CARB", 245, 8.5, 50.0, 1.5, True),
    ("Molokhia (cooked)", "VEGETABLE", 60, 4.5, 6.0, 2.0, True),
    ("Mahshi Cabbage", "COMPOSITE", 150, 3.5, 22.0, 5.5, True),
    ("Mahshi Grape Leaves", "COMPOSITE", 175, 3.0, 24.0, 7.5, True),
    ("Bechamel Pasta", "COMPOSITE", 210, 9.0, 22.0, 10.0, True),
    ("Egyptian Feta (Gebna Beida)", "DAIRY", 265, 14.0, 4.0, 21.0, True),
    ("Roumy Cheese", "DAIRY", 380, 25.0, 2.0, 30.0, True),
    ("Areesh Cheese", "DAIRY", 100, 12.0, 4.0, 4.0, True),
    ("Halawa Tehina", "FAT", 500, 12.0, 50.0, 30.0, True),
    ("Eggplant Moussaka (Egyptian)", "COMPOSITE", 130, 2.5, 12.0, 8.5, True),
    ("Hawawshi", "COMPOSITE", 280, 15.0, 26.0, 13.0, True),
    ("Feteer Meshaltet", "CARB", 380, 8.0, 42.0, 20.0, True),
    ("Rice with Vermicelli", "CARB", 150, 3.5, 30.0, 2.5, True),
    ("Lentil Soup (Shorbat Ads)", "COMPOSITE", 95, 5.5, 15.0, 1.5, True),
    ("Sugar Cane Juice", "DRINK", 70, 0.2, 18.0, 0.1, True),
    ("Karkade (unsweetened)", "DRINK", 5, 0.0, 1.0, 0.0, True),
    ("Dates (Egyptian, dried)", "FRUIT", 280, 2.5, 70.0, 0.4, True),
    # --- Proteins ---------------------------------------------------------
    ("Chicken Breast (grilled)", "PROTEIN", 165, 31.0, 0.0, 3.6, False),
    ("Chicken Thigh (grilled)", "PROTEIN", 209, 26.0, 0.0, 11.0, False),
    ("Beef Mince (lean, cooked)", "PROTEIN", 215, 26.0, 0.0, 12.0, False),
    ("Beef Steak (grilled)", "PROTEIN", 250, 27.0, 0.0, 15.0, False),
    ("Tilapia (grilled)", "PROTEIN", 128, 26.0, 0.0, 2.7, False),
    ("Bolti Fish (fried)", "PROTEIN", 210, 22.0, 4.0, 12.0, False),
    ("Tuna (canned in water)", "PROTEIN", 116, 26.0, 0.0, 1.0, False),
    ("Salmon (grilled)", "PROTEIN", 208, 20.0, 0.0, 13.0, False),
    ("Shrimp (boiled)", "PROTEIN", 99, 24.0, 0.2, 0.3, False),
    ("Whole Egg (boiled)", "PROTEIN", 155, 13.0, 1.1, 11.0, False),
    ("Egg White", "PROTEIN", 52, 11.0, 0.7, 0.2, False),
    ("Whey Protein Powder", "PROTEIN", 400, 80.0, 8.0, 6.0, False),
    ("Liver (cooked)", "PROTEIN", 175, 26.0, 4.0, 5.0, False),
    # --- Carbs ------------------------------------------------------------
    ("White Rice (cooked)", "CARB", 130, 2.7, 28.0, 0.3, False),
    ("Brown Rice (cooked)", "CARB", 123, 2.6, 26.0, 1.0, False),
    ("Pasta (cooked)", "CARB", 158, 5.8, 31.0, 0.9, False),
    ("Oats (dry)", "CARB", 389, 17.0, 66.0, 7.0, False),
    ("Potato (boiled)", "CARB", 87, 2.0, 20.0, 0.1, False),
    ("Sweet Potato (baked)", "CARB", 90, 2.0, 21.0, 0.1, False),
    ("Whole Wheat Bread", "CARB", 247, 13.0, 41.0, 3.4, False),
    ("Chickpeas (cooked)", "CARB", 164, 8.9, 27.0, 2.6, False),
    ("White Beans (cooked)", "CARB", 140, 9.7, 25.0, 0.5, False),
    ("Lentils (cooked)", "CARB", 116, 9.0, 20.0, 0.4, False),
    # --- Dairy ------------------------------------------------------------
    ("Full-Fat Milk", "DAIRY", 61, 3.2, 4.8, 3.3, False),
    ("Skimmed Milk", "DAIRY", 34, 3.4, 5.0, 0.1, False),
    ("Greek Yoghurt (plain)", "DAIRY", 59, 10.0, 3.6, 0.4, False),
    ("Zabady (plain yoghurt)", "DAIRY", 61, 3.5, 4.7, 3.3, False),
    ("Mozzarella", "DAIRY", 300, 22.0, 2.2, 22.0, False),
    # --- Fats -------------------------------------------------------------
    ("Olive Oil", "FAT", 884, 0.0, 0.0, 100.0, False),
    ("Sunflower Oil", "FAT", 884, 0.0, 0.0, 100.0, False),
    ("Butter", "FAT", 717, 0.9, 0.1, 81.0, False),
    ("Tahina", "FAT", 595, 17.0, 21.0, 54.0, False),
    ("Peanut Butter", "FAT", 588, 25.0, 20.0, 50.0, False),
    ("Almonds", "FAT", 579, 21.0, 22.0, 50.0, False),
    ("Walnuts", "FAT", 654, 15.0, 14.0, 65.0, False),
    ("Peanuts (roasted)", "FAT", 567, 26.0, 16.0, 49.0, False),
    # --- Vegetables -------------------------------------------------------
    ("Cucumber", "VEGETABLE", 15, 0.7, 3.6, 0.1, False),
    ("Tomato", "VEGETABLE", 18, 0.9, 3.9, 0.2, False),
    ("Green Salad (mixed)", "VEGETABLE", 20, 1.2, 3.5, 0.2, False),
    ("Broccoli (steamed)", "VEGETABLE", 35, 2.4, 7.2, 0.4, False),
    ("Spinach (cooked)", "VEGETABLE", 23, 2.9, 3.6, 0.4, False),
    ("Green Beans (cooked)", "VEGETABLE", 35, 1.9, 7.9, 0.1, False),
    ("Okra (cooked)", "VEGETABLE", 40, 1.9, 7.5, 0.2, False),
    ("Carrot", "VEGETABLE", 41, 0.9, 10.0, 0.2, False),
    ("Onion", "VEGETABLE", 40, 1.1, 9.3, 0.1, False),
    # --- Fruit ------------------------------------------------------------
    ("Banana", "FRUIT", 89, 1.1, 23.0, 0.3, False),
    ("Apple", "FRUIT", 52, 0.3, 14.0, 0.2, False),
    ("Orange", "FRUIT", 47, 0.9, 12.0, 0.1, False),
    ("Mango", "FRUIT", 60, 0.8, 15.0, 0.4, False),
    ("Grapes", "FRUIT", 69, 0.7, 18.0, 0.2, False),
    ("Watermelon", "FRUIT", 30, 0.6, 7.6, 0.2, False),
    ("Guava", "FRUIT", 68, 2.6, 14.0, 1.0, False),
    ("Strawberries", "FRUIT", 32, 0.7, 7.7, 0.3, False),
]

SUPPLEMENTS = [
    ("Whey Protein", "Post-workout or to fill a protein gap."),
    ("Creatine Monohydrate", "5g daily, timing does not matter."),
    ("Vitamin D3", "Common deficiency; take with a fat-containing meal."),
    ("Omega 3 (Fish Oil)", "With a meal."),
    ("Magnesium", "Evening; may help sleep quality."),
    ("Multivitamin", "With breakfast."),
    ("Caffeine", "Pre-workout. Avoid late in the day."),
]


def seed_foods(apps, schema_editor):
    FoodItem = apps.get_model("nutrition", "FoodItem")
    Supplement = apps.get_model("nutrition", "Supplement")

    for name, category, kcal, protein, carbs, fat, staple in FOODS:
        FoodItem.objects.get_or_create(
            name=name,
            defaults={
                "category": category,
                "calories_per_100g": kcal,
                "protein_per_100g": protein,
                "carbs_per_100g": carbs,
                "fats_per_100g": fat,
                "is_egyptian_staple": staple,
            },
        )

    for name, notes in SUPPLEMENTS:
        Supplement.objects.get_or_create(name=name, defaults={"notes": notes})


def unseed_foods(apps, schema_editor):
    FoodItem = apps.get_model("nutrition", "FoodItem")
    Supplement = apps.get_model("nutrition", "Supplement")

    # Leave anything already used in a plan alone: reversing a migration should
    # not silently rewrite a client's meals.
    FoodItem.objects.filter(
        name__in=[f[0] for f in FOODS], meal_entries__isnull=True
    ).delete()
    Supplement.objects.filter(
        name__in=[s[0] for s in SUPPLEMENTS], schedules__isnull=True
    ).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("nutrition", "0002_fooditem_supplement_alter_meal_options_and_more"),
    ]

    operations = [
        migrations.RunPython(seed_foods, unseed_foods),
    ]
