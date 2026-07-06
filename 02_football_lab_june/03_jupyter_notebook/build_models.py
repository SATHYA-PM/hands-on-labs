"""
Build script: runs Tasks 1-7 from the notebook to produce
models/match_predictor.pkl and models/team_data.pkl
"""
from pathlib import Path
from collections import defaultdict
import requests
import pandas as pd
import joblib
from sklearn.ensemble import RandomForestClassifier

# ---------- Task 2: Load dataset ----------
data_dir = Path("data")
data_dir.mkdir(exist_ok=True)
csv_path = data_dir / "results.csv"

# Try local copy first (already in 04_data)
local_copy = Path("../04_data/results.csv")
if not csv_path.exists():
    if local_copy.exists():
        import shutil
        shutil.copy(local_copy, csv_path)
        print(f"Copied from {local_copy}")
    else:
        url = "https://raw.githubusercontent.com/SATHYA-PM/hands-on-labs/main/02_football_lab_june/04_data/results.csv"
        print(f"Downloading dataset...")
        r = requests.get(url, timeout=60)
        r.raise_for_status()
        csv_path.write_bytes(r.content)
        print(f"Saved {csv_path.stat().st_size/1024:.1f} KB")
else:
    print(f"Using cached {csv_path}")

matches = pd.read_csv(csv_path, parse_dates=["date"])
print(f"Shape: {matches.shape}  |  {matches['date'].min().date()} to {matches['date'].max().date()}")

# ---------- Task 4: Feature engineering ----------
major_tournaments = {
    "Soccer World Cup", "Soccer World Cup qualification",
    "UEFA Euro", "UEFA Euro qualification",
    "Copa América", "African Cup of Nations",
}

m = matches[matches["date"] >= "1990-01-01"].sort_values("date").reset_index(drop=True)
team_history = defaultdict(list)

def winrate(hist):
    return sum(1 for _, _, w in hist if w == 1) / len(hist) if hist else 0.5

def goal_avg(hist):
    return sum(gf for gf, _, _ in hist) / len(hist) if hist else 1.0

def recent_form(hist):
    last = hist[-10:]
    return sum(1 for _, _, w in last if w == 1) / len(last) if len(last) == 10 else 0.5

rows = []
for _, row in m.iterrows():
    home, away = row["home_team"], row["away_team"]
    h_hist, a_hist = team_history[home], team_history[away]
    if row["home_score"] > row["away_score"]:
        outcome, home_won, away_won = 0, 1, 0
    elif row["home_score"] < row["away_score"]:
        outcome, home_won, away_won = 2, 0, 1
    else:
        outcome, home_won, away_won = 1, 0, 0
    rows.append({
        "date": row["date"], "home_team": home, "away_team": away,
        "team_a_winrate": winrate(h_hist), "team_b_winrate": winrate(a_hist),
        "team_a_goal_avg": goal_avg(h_hist), "team_b_goal_avg": goal_avg(a_hist),
        "team_a_recent_form": recent_form(h_hist), "team_b_recent_form": recent_form(a_hist),
        "is_neutral": int(row["neutral"]),
        "is_major_tournament": 1 if row["tournament"] in major_tournaments else 0,
        "outcome": outcome,
    })
    team_history[home].append((row["home_score"], row["away_score"], home_won))
    team_history[away].append((row["away_score"], row["home_score"], away_won))

features_df = pd.DataFrame(rows)
print(f"Features shape: {features_df.shape}")

# ---------- Task 5: Train/test split ----------
feature_cols = [
    "team_a_winrate", "team_b_winrate",
    "team_a_goal_avg", "team_b_goal_avg",
    "team_a_recent_form", "team_b_recent_form",
    "is_neutral", "is_major_tournament",
]
cutoff = pd.Timestamp("2018-01-01")
X_train = features_df.loc[features_df["date"] < cutoff, feature_cols]
y_train = features_df.loc[features_df["date"] < cutoff, "outcome"]
X_test  = features_df.loc[features_df["date"] >= cutoff, feature_cols]
y_test  = features_df.loc[features_df["date"] >= cutoff, "outcome"]
print(f"Train: {X_train.shape}  Test: {X_test.shape}")

# ---------- Task 6: Train model ----------
print("Training RandomForest...")
model = RandomForestClassifier(n_estimators=200, max_depth=12, random_state=42, n_jobs=-1)
model.fit(X_train, y_train)
from sklearn.metrics import accuracy_score
acc = accuracy_score(y_test, model.predict(X_test))
print(f"Test accuracy: {acc*100:.2f}%")

# ---------- Task 7: Build team_stats & save ----------
models_dir = Path("models")
models_dir.mkdir(exist_ok=True)

wc_qual = matches[matches["tournament"] == "Soccer World Cup qualification"]
soccer_teams = set(pd.concat([wc_qual["home_team"], wc_qual["away_team"]]).unique())

team_stats = {}
for team in pd.concat([matches["home_team"], matches["away_team"]]).unique():
    if team not in soccer_teams:
        continue
    home = matches[matches["home_team"] == team]
    away = matches[matches["away_team"] == team]
    total = len(home) + len(away)
    if total < 30:
        continue
    home_wins = int((home["home_score"] > home["away_score"]).sum())
    away_wins = int((away["away_score"] > away["home_score"]).sum())
    total_goals = int(home["home_score"].sum() + away["away_score"].sum())
    last10 = matches[(matches["home_team"] == team) | (matches["away_team"] == team)].sort_values("date").tail(10)
    if len(last10) == 10:
        wins = sum(1 for _, r in last10.iterrows() if
                   (r["home_team"] == team and r["home_score"] > r["away_score"]) or
                   (r["away_team"] == team and r["away_score"] > r["home_score"]))
        rf = wins / 10
    else:
        rf = 0.5
    team_stats[team] = {"winrate": (home_wins+away_wins)/total, "goal_avg": total_goals/total,
                        "recent_form": rf, "matches_played": total}

joblib.dump(model, models_dir / "match_predictor.pkl")
joblib.dump({"team_stats": team_stats, "feature_cols": feature_cols}, models_dir / "team_data.pkl")
print(f"\nSaved model + team_data for {len(team_stats)} teams to models/")
eligible = [(t, s) for t, s in team_stats.items() if s["matches_played"] >= 100]
for team, s in sorted(eligible, key=lambda x: -x[1]["winrate"])[:5]:
    print(f"  {team:<25} winrate={s['winrate']:.3f}  matches={s['matches_played']}")
