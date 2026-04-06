import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import train_test_split
from sklearn.metrics import *

#leer dataset
df = pd.read_csv("clima_historico.csv")

#variables
features = df.select_dtypes(include=["number"])
target = df["condition"]

#split
Xtrain, Xtest, ytrain, ytest = train_test_split(features, target, test_size=0.2, stratify=target, random_state=42)

#modelo
rf = RandomForestClassifier(n_estimators=100, random_state=42)
rf.fit(Xtrain, ytrain)

#predicción
pred = rf.predict(Xtest)

#resultados
print("Random Forest Results")
print("Accuracy:", accuracy_score(ytest, pred))
print("Precision:", precision_score(ytest, pred, average="macro"))
print("Recall:", recall_score(ytest, pred, average="macro"))
print("F1:", f1_score(ytest, pred, average="macro"))
print("Classification Report:\n", classification_report(ytest, pred))