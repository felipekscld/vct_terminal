# Skill: VCT Odds Extractor (Betano & Bet365)

## Purpose
Extract betting odds for a Valorant VCT match from Betano and Bet365. Return structured JSON.

---

## BETANO (https://www.betano.com)

### Navigation Steps
1. Open https://www.betano.com
2. Click **ESPORTS** (bottom left sidebar, may need to scroll)
3. In "Todas as Competições", find **Valorant**, expand it
4. Click the tournament name (e.g., "VCT 2026 Challenger Series")
5. You'll see match cards with teams listed

### On the Match Page
**Important:** Markets are presented in **collapsible sections** (expandable headings). Some markets may be closed by default. Click the section header to expand.

### Markets to Extract (Portuguese Labels on Betano)

#### 1. **Vencedor** (Match Winner)
- Located: Top of the section, always visible
- Format: `Team1: X.XX | Team2: Y.YY`
- Capture:
  ```json
  {
    "bookmaker": "betano",
    "market_type": "match_winner",
    "selection": "Team1 name",
    "odds_value": 1.80,
    "map_number": null
  }
  ```

#### 2. **Vencedor do Mapa (Mapa 1/2/3)** (Map Winners)
- One section per map (e.g., "Vencedor do Mapa (Mapa 1)")
- Expand each map section
- Format: `Team1: A.AA | Team2: B.BB`
- **BO3 detection:** If only Mapa 1, 2, 3 exist → it's BO3. If more → BO5
- Capture for each:
  ```json
  {
    "bookmaker": "betano",
    "market_type": "map_winner",
    "selection": "Team1 name",
    "odds_value": 1.82,
    "map_number": 1
  }
  ```

#### 3. **Handicap do Jogo** (Match Handicap)
- Section: "Handicap do Jogo"
- Format: `Team1 -1.5: X.XX | Team2 +1.5: Y.YY` (or variations)
- Extract both sides. Handicap value might be -1.5, +1.5, etc.
- Capture:
  ```json
  {
    "bookmaker": "betano",
    "market_type": "handicap_match",
    "selection": "Team1 -1.5",
    "odds_value": 3.15,
    "map_number": null
  }
  ```

#### 4. **Total de Mapas** (Total Maps)
- Section: "Total de Mapas"
- Format: `Mais de 2.5: A.AA | Menos de 2.5: B.BB`
- Capture both:
  ```json
  {
    "bookmaker": "betano",
    "market_type": "total_maps",
    "selection": "Over 2.5",
    "odds_value": 1.87,
    "map_number": null
  }
  ```

#### 5. **Resultado Correto** (Correct Score)
- Section: "Resultado Correto"
- Format: Buttons like `2-0: X.XX`, `2-1: Y.YY`, `1-2: Z.ZZ`, `0-2: W.WW`
- Capture each:
  ```json
  {
    "bookmaker": "betano",
    "market_type": "correct_score",
    "selection": "2-0",
    "odds_value": 3.15,
    "map_number": null
  }
  ```

#### 6. **Outros Especiais** (Special Markets / Overtime Markets)
- Section: "Outros Especiais"
- **IMPORTANT:** This section contains multiple market types. Expand ALL collapsible sections.
- Capture everything you find. New market types may appear. See "Market Types Reference" below.

**Markets Found in This Section:**

##### 6a. **Total de Rounds Ímpares/pares (Mapa N)** (Odd/Even Total Rounds)
- Applies to individual maps
- Format: `Ímpar (Odd): X.XX | Par (Even): Y.YY`
- Capture as:
  ```json
  {
    "bookmaker": "betano",
    "market_type": "total_rounds_parity",
    "selection": "Odd",
    "odds_value": 2.27,
    "map_number": 3
  }
  ```

##### 6b. **Team Para ganhar pelo menos um mapa** (Team to Win At Least 1 Map)
- For each team, separate section
- Format: `Sim (Yes): X.XX | Não (No): Y.YY`
- Capture:
  ```json
  {
    "bookmaker": "betano",
    "market_type": "team_win_min_maps",
    "selection": "SaD Esports - Yes",
    "odds_value": 1.26,
    "map_number": null
  }
  ```

##### 6c. **Número de mapas Par/Ímpar** (Even/Odd Number of Maps)
- Collapsible section (click "CA" to expand)
- Format: `Par (Even): X.XX | Ímpar (Odd): Y.YY`
- Capture:
  ```json
  {
    "bookmaker": "betano",
    "market_type": "total_maps_parity",
    "selection": "Even",
    "odds_value": 1.XX,
    "map_number": null
  }
  ```

##### 6d. **Prorrogação (Mapa 1/2/3)** (Overtime on Map)
- Separate section for each map with OT possibility
- Format: `Sim (Yes): X.XX | Não (No): Y.YY`
- Capture both selections:
  ```json
  {
    "bookmaker": "betano",
    "market_type": "overtime",
    "selection": "Yes",
    "odds_value": 5.60,
    "map_number": 1
  },
  {
    "bookmaker": "betano",
    "market_type": "overtime",
    "selection": "No",
    "odds_value": 1.12,
    "map_number": 1
  }
  ```

---

## Market Types Reference

**Standard Types (documented above):**
- `match_winner` — Winner of the match
- `map_winner` — Winner of a specific map
- `handicap_match` — Match-level handicap (e.g., Team -1.5)
- `total_maps` — Over/Under on total maps (e.g., Over 2.5)
- `correct_score` — Series final score (2-0, 2-1, etc.)
- `overtime` — Overtime Yes/No on a specific map
- `total_rounds_parity` — Odd/Even total rounds on a map
- `team_win_min_maps` — Team to win at least 1 map (Yes/No)
- `total_maps_parity` — Odd/Even total number of maps

**If You Find a New Market Type:**

If a market section appears that isn't listed above:
1. **Capture it anyway** with a descriptive `market_type` name (e.g., `first_blood_map_1`, `team_score_over_20`, `pistol_round_winner`)
2. **Include in JSON output** — don't skip it
3. **Examples:**
   ```json
   {
     "bookmaker": "betano",
     "market_type": "first_map_winner",
     "selection": "Team1",
     "odds_value": 1.75,
     "map_number": null
   }
   ```
4. **Future updates:** I'll review the data and add new market types to this skill as they become common

---

## BET365 (https://www.bet365.com)

### Navigation Steps
1. Open https://www.bet365.com
2. Go to **Esports** > **Valorant**
3. Find the same match by date/teams
4. Extract markets in similar format

### Markets on Bet365
Bet365 layout differs from Betano. Look for:
- Match Winner
- Map Winners (if available)
- Handicap
- Totals
- Correct Score

Extract in same JSON format (change `bookmaker` to `"bet365"`).

---

## UI Handling Tips ⚠️

### Collapsible Sections
- Sections like "Vencedor do Mapa (Mapa 1)" may be **collapsed by default**
- Look for a **disclosure triangle (▼/▶)** or **"CA" button** (Clique Aqui = "Click Here")
- **Click it to expand** and reveal odds
- Don't assume markets are missing — check if they're just hidden

### Dynamic Content
- Odds may load asynchronously after page renders
- **Wait 2-3 seconds** after navigation before extracting
- Scroll down to ensure all sections are visible
- Some odds may be disabled (greyed out) — skip those

### Geolocation / Age Gate
- Click **"18+" or "Confirm"** buttons if prompted
- Dismiss any cookie/privacy banners

---

## Output Format

Return ONLY a JSON array (no markdown, no extra text):

```json
[
  {
    "bookmaker": "betano",
    "market_type": "match_winner",
    "selection": "SaD Esports",
    "odds_value": 1.80,
    "map_number": null
  },
  {
    "bookmaker": "betano",
    "market_type": "map_winner",
    "selection": "SaD Esports",
    "odds_value": 1.82,
    "map_number": 1
  },
  {
    "bookmaker": "betano",
    "market_type": "total_maps",
    "selection": "Over 2.5",
    "odds_value": 1.87,
    "map_number": null
  },
  {
    "bookmaker": "betano",
    "market_type": "correct_score",
    "selection": "2-1",
    "odds_value": 3.25,
    "map_number": null
  }
]
```

---

## Checklist Before Returning

- [ ] All sections expanded: Vencedor, each Map, Handicap, Total Mapas, Resultado Correto, **Outros Especiais**
- [ ] **Prorrogação (OT)** odds captured for each map (Sim/Não both)
- [ ] **Total de Rounds Ímpares/pares** captured for each map
- [ ] **Team to Win At Least 1 Map** odds captured for each team
- [ ] **Total Maps Parity** (Even/Odd) captured
- [ ] Both teams captured for each market (where applicable)
- [ ] Odds are decimal format (X.XX)
- [ ] No typos in team names
- [ ] Map numbers are correct (1, 2, 3, etc.)
- [ ] BO3 vs BO5 correctly identified
- [ ] **All special/combo markets** extracted from "Outros Especiais"
- [ ] **Any unknown markets** captured with descriptive `market_type` names
