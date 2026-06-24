PY = venv/bin/python

# Add or refresh one race, then retrain + refresh manifest (keeps data in sync):
#   make race YEAR=2024 RACE="Monaco"
race:
	$(PY) -m pipeline.update --year $(YEAR) --race "$(RACE)"

# Re-export every known race and retrain.
refresh:
	$(PY) -m pipeline.update --all

# Consistency report (which races are complete, is the model in sync).
check:
	$(PY) -m pipeline.update --check

# Train the pace model on the current race set.
model:
	$(PY) -m pipeline.train_model

# Run the web app.
web:
	cd web && npm run dev

# Run the strategist retrieval eval.
eval:
	cd web && npm run eval:strategist

.PHONY: race refresh check model web eval
