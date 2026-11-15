"""Builds notebooks/FinPilot_results.ipynb (run from the project root).

    .venv/bin/python notebooks/build_notebook.py            # build only
    .venv/bin/python notebooks/build_notebook.py --execute  # build and run, saving outputs
"""
import sys
from pathlib import Path

import nbformat as nbf

md = nbf.v4.new_markdown_cell
code = nbf.v4.new_code_cell

cells = [
    md("# FinPilot — results notebook\n"
       "Veritas AI High School Hackathon 2026 · AI + Finance.\n\n"
       "This notebook rebuilds the data, retrains every model and prints the results on test data the models never saw.\n\n"
       "> **This project is a prototype and is not financial advice.**"),
    md("## 0. Setup\nIn Colab this clones the repository and installs the packages. Locally it just uses the project folder."),
    code("import os, sys, json, subprocess\n"
         "if 'google.colab' in sys.modules:\n"
         "    !git clone -q https://github.com/masalihx/FinFam.git\n"
         "    %cd FinFam\n"
         "    !pip -q install -r requirements.txt\n"
         "elif os.path.basename(os.getcwd()) == 'notebooks':\n"
         "    os.chdir('..')\n"
         "PY = sys.executable\n"
         "def run(script):\n"
         "    out = subprocess.run([PY, script], capture_output=True, text=True)\n"
         "    print('\\n'.join(l for l in (out.stdout + out.stderr).splitlines() if 'Warning' not in l and 'warn' not in l))\n"
         "print('Ready:', os.path.basename(os.getcwd()))"),
    md("## 1. Data\nOpen synthetic bank data for 100 US families (Misata, CC BY 4.0) and 68k bank descriptions (DoDataThings, MIT), mapped to 16 shared categories."),
    code("run('ml/data_prep.py')"),
    md("## 2. ML part 1 — categorization\nTrained on one dataset, tested on 50 families from another dataset; then learning from user corrections."),
    code("run('ml/train_categorizer.py')"),
    md("## 3. ML part 3 — overspend risk\nOn day 5/10/15/20/25: will this family end the month above its usual level in a category? Train 2025, test Apr–Sep 2026."),
    code("run('ml/train_overspend.py')\nrun('ml/check_live_features.py')"),
    md("## 4. ML part 2 — recurring payments\nFinds rent, bills and subscriptions, predicts the next payment. 30% of families held out."),
    code("run('ml/train_recurring.py')"),
    md("## 5. ML part 4 — market price\nRidge regression on product titles (Amazon Products 2023). Gemini comparison and the hybrid blend need a `GEMINI_API_KEY`; without it the saved results are shown."),
    code("if os.environ.get('GEMINI_API_KEY'):\n"
         "    run('ml/train_price.py'); run('ml/price_hybrid.py'); run('ml/gemini_baselines.py')\n"
         "print(json.dumps(json.load(open('ml/results/price_hybrid.json'))['test'], indent=1))"),
    md("## 6. ML part 5 — verdict backtest (the main number)\nEvery online purchase of $20+ in Apr–Sep 2026 is replayed as if the extension were open. All methods postpone the same number of purchases."),
    code("run('ml/backtest_verdict.py')"),
    md("## 7. Assistant intents"),
    code("run('ml/train_intent.py')"),
    md("## 8. Summary tables and charts"),
    code("import pandas as pd, matplotlib.pyplot as plt\n"
         "R = {n: json.load(open(f'ml/results/{n}.json')) for n in ['categorizer','overspend','recurring','price_hybrid','backtest_verdict','intent','gemini_baselines']}\n"
         "rows = [\n"
         " ('Categorization (macro-F1)', 'keywords', R['categorizer']['test']['keyword_baseline'], R['categorizer']['test']['model']),\n"
         " ('Overspend (PR-AUC)', 'proportion', R['overspend']['test']['baseline_proportion']['pr_auc'], R['overspend']['test']['model']['pr_auc']),\n"
         " ('Recurring (F1)', '3 times in 3 months', R['recurring']['detection']['baseline_3_times_3_months']['f1'], R['recurring']['detection']['model']['f1']),\n"
         " ('Market price (within ±25%)', 'category median', R['price_hybrid']['test']['baseline_category_median']['within_25pct'], R['price_hybrid']['test']['hybrid']['within_25pct']),\n"
         " ('Assistant intents (macro-F1)', 'keywords', R['intent']['keyword_baseline']['macro_f1'], R['intent']['model']['macro_f1']),\n"
         "]\n"
         "pd.DataFrame(rows, columns=['Task', 'Baseline', 'Baseline score', 'Our model'])"),
    code("b = R['backtest_verdict']['same_number_of_warnings']\n"
         "names = {'rule_50_30_20':'50/30/20 rule','proportion':'Proportion','overspend_model_only':'Risk model only','verdict':'FinPilot verdict'}\n"
         "vals = [b[k]['avoided_per_family_month_usd'] for k in names]\n"
         "fig, ax = plt.subplots(figsize=(7,3.2))\n"
         "ax.barh(list(names.values()), vals, color=['#94a3b8','#94a3b8','#14b8a6','#0f766e'])\n"
         "for i, v in enumerate(vals): ax.text(v+3, i, f'${v:.0f}', va='center')\n"
         "ax.set_xlabel('Overspending avoided, $ per family per month (same number of warnings)')\n"
         "ax.spines[['top','right']].set_visible(False); plt.tight_layout(); plt.show()"),
    code("d = R['overspend']['by_day']\n"
         "days = sorted(d, key=int)\n"
         "fig, ax = plt.subplots(figsize=(7,3.2))\n"
         "ax.plot([int(x) for x in days], [d[x]['proportion']['recall'] for x in days], marker='o', label='Proportion rule', color='#94a3b8')\n"
         "ax.plot([int(x) for x in days], [d[x]['model']['recall'] for x in days], marker='o', label='Our model', color='#0f766e')\n"
         "ax.set_xlabel('Day of month'); ax.set_ylabel('Share of overspends caught'); ax.legend(); ax.spines[['top','right']].set_visible(False)\n"
         "plt.tight_layout(); plt.show()"),
    md("## 9. Where it fails\nError examples saved by each script:"),
    code("print('Verdict, flagged but the month ended fine:')\n"
         "for e in R['backtest_verdict']['error_examples']['not_worth_it_but_fine']: print(' ', e['label'], e['price'], e['description'][:40])\n"
         "print('Verdict, said Buy but the month went over:')\n"
         "for e in R['backtest_verdict']['error_examples']['buy_but_harmful']: print(' ', e['label'], e['price'], e['description'][:40])\n"
         "print('Categorization:')\nfor e in R['categorizer']['error_examples'][:4]: print(' ', e)\n"
         "print('Recurring false alarms:')\nfor e in R['recurring']['error_examples']['false_alarm']: print(' ', e['key'])\n"
         "print('Assistant:')\nfor e in R['intent']['model_errors'][:4]: print(' ', e)"),
    md("> This project is a prototype and is not financial advice."),
]

nb = nbf.v4.new_notebook(cells=cells, metadata={"kernelspec": {"name": "python3", "display_name": "Python 3"},
                                                "colab": {"provenance": []}})
out = Path("notebooks/FinPilot_results.ipynb")
if "--execute" in sys.argv:
    from nbconvert.preprocessors import ExecutePreprocessor
    ExecutePreprocessor(timeout=1800, kernel_name="python3").preprocess(nb, {"metadata": {"path": "."}})
nbf.write(nb, out)
print(f"Wrote {out}")
