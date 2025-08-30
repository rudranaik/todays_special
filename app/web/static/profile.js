const apiBase = ""; // same-origin FastAPI app

const els = {
    profileForm: document.getElementById("profile-form"),
    userName: document.getElementById("user_name"),
    age: document.getElementById("age"),
    gender: document.getElementById("gender"),
    height: document.getElementById("height"),
    weight: document.getElementById("weight"),
    country: document.getElementById("country"),
    macroGoals: document.getElementById("macro-goals"),
    meals: document.getElementById("meals"),
    addMealBtn: document.getElementById("add-meal"),
};

let profile = null;

async function loadProfile() {
    try {
        const r = await fetch(`${apiBase}/api/v1/profile`);
        if (r.ok) {
            profile = await r.json();
            renderProfile();
        } else {
            // If no profile exists, create a default one
            profile = {
                user_name: "",
                age: 30,
                gender: "male",
                height: 175,
                weight: 70,
                country: "",
                macro_goals: {
                    calories: 2000,
                    protein: 150,
                    carbohydrates: 250,
                    fats: 60,
                },
                meals: [
                    { name: "Breakfast", calories: 600, protein: 45, carbohydrates: 75, fats: 18 },
                    { name: "Lunch", calories: 800, protein: 60, carbohydrates: 100, fats: 24 },
                    { name: "Dinner", calories: 600, protein: 45, carbohydrates: 75, fats: 18 },
                ],
            };
            renderProfile();
        }
    } catch (e) {
        console.error("Failed to load profile", e);
    }
}

function renderProfile() {
    if (!profile) return;

    els.userName.value = profile.user_name;
    els.age.value = profile.age;
    els.gender.value = profile.gender;
    els.height.value = profile.height;
    els.weight.value = profile.weight;
    els.country.value = profile.country;

    renderMacroGoals();
    renderMeals();
}

function renderMacroGoals() {
    const goals = profile.macro_goals;
    els.macroGoals.innerHTML = `
        <div class="row">
            <label>Calories: <input type="number" id="calories" value="${goals.calories}" /></label>
            <label>Protein (g): <input type="number" id="protein" value="${goals.protein}" /></label>
        </div>
        <div class="row">
            <label>Carbohydrates (g): <input type="number" id="carbohydrates" value="${goals.carbohydrates}" /></label>
            <label>Fats (g): <input type="number" id="fats" value="${goals.fats}" /></label>
        </div>
    `;
}

function renderMeals() {
    els.meals.innerHTML = "";
    profile.meals.forEach((meal, i) => {
        const mealEl = document.createElement("div");
        mealEl.className = "meal-item";
        mealEl.innerHTML = `
            <div class="meal-header">
                <h3>${meal.name}</h3>
                <button class="delete-btn" data-del="${i}">Delete</button>
            </div>
            <div class="form-grid">
                <label>Calories: <input type="number" data-i="${i}" data-k="calories" value="${meal.calories}"/></label>
                <label>Protein (g): <input type="number" data-i="${i}" data-k="protein" value="${meal.protein}"/></label>
                <label>Carbs (g): <input type="number" data-i="${i}" data-k="carbohydrates" value="${meal.carbohydrates}"/></label>
                <label>Fats (g): <input type="number" data-i="${i}" data-k="fats" value="${meal.fats}"/></label>
            </div>
        `;
        els.meals.appendChild(mealEl);
    });

    els.meals.querySelectorAll("input").forEach(inp => {
        inp.addEventListener("change", () => {
            const i = Number(inp.dataset.i);
            const k = inp.dataset.k;
            let v = inp.value;
            if (k !== "name") v = Number(v);
            profile.meals[i][k] = v;
        });
    });

    els.meals.querySelectorAll(".delete-btn").forEach(btn => {
        btn.addEventListener("click", () => {
            const i = Number(btn.dataset.del);
            profile.meals.splice(i, 1);
            renderMeals();
        });
    });
}

els.addMealBtn.addEventListener("click", () => {
    profile.meals.push({
        name: "New Meal",
        calories: 0,
        protein: 0,
        carbohydrates: 0,
        fats: 0,
    });
    renderMeals();
});

els.profileForm.addEventListener("submit", async (ev) => {
    ev.preventDefault();

    profile.user_name = els.userName.value;
    profile.age = Number(els.age.value);
    profile.gender = els.gender.value;
    profile.height = Number(els.height.value);
    profile.weight = Number(els.weight.value);
    profile.country = els.country.value;

    profile.macro_goals.calories = Number(document.getElementById("calories").value);
    profile.macro_goals.protein = Number(document.getElementById("protein").value);
    profile.macro_goals.carbohydrates = Number(document.getElementById("carbohydrates").value);
    profile.macro_goals.fats = Number(document.getElementById("fats").value);

    try {
        const r = await fetch(`${apiBase}/api/v1/profile`, {
            method: "PUT",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(profile),
        });
        if (r.ok) {
            profile = await r.json();
            renderProfile();
            alert("Profile saved!");
        } else {
            alert("Failed to save profile");
        }
    } catch (e) {
        console.error("Failed to save profile", e);
        alert("Failed to save profile");
    }
});

loadProfile();
