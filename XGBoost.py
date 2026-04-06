import pandas as pd
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import LabelEncoder
from xgboost import XGBClassifier
from sklearn.metrics import accuracy_score, precision_score, recall_score, f1_score, classification_report

#data
dataset = pd.read_csv("clima_historico.csv")

X = dataset.select_dtypes(include=["number"])
y = dataset["condition"]

#codificar labels
le = LabelEncoder()
y_encoded = le.fit_transform(y)

#separación de datos
X_tr, X_te, y_tr, y_te = train_test_split(X, y_encoded, test_size=0.2, stratify=y_encoded, random_state=42)

#modelo
xgb = XGBClassifier(eval_metric="mlogloss")
xgb.fit(X_tr, y_tr)

#predicciones
y_hat = xgb.predict(X_te)

#métricas
print("XGBoost Performance")
print(f"Accuracy: {accuracy_score(y_te, y_hat)}")
print(f"Precision: {precision_score(y_te, y_hat, average='macro')}")
print(f"Recall: {recall_score(y_te, y_hat, average='macro')}")
print(f"F1-score: {f1_score(y_te, y_hat, average='macro')}")
print(classification_report(y_te, y_hat))