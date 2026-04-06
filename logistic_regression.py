import pandas as pd
from sklearn.model_selection import train_test_split
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, precision_score, recall_score, f1_score, classification_report

#datos
data = pd.read_csv("clima_historico.csv")

#variables
X = data.select_dtypes(include=["number"])
y = data["condition"]

#división de datos
X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, stratify=y, random_state=42)

#modelo
modelo = LogisticRegression(max_iter=1000)

#entrenamiento
modelo.fit(X_train, y_train)

#predicciones
y_pred = modelo.predict(X_test)

#evaluación
print("=== Logistic Regression ===")
print("Accuracy:", accuracy_score(y_test, y_pred))
print("Precision:", precision_score(y_test, y_pred, average="macro"))
print("Recall:", recall_score(y_test, y_pred, average="macro"))
print("F1-score:", f1_score(y_test, y_pred, average="macro"))
print("\nReporte de clasificación:\n", classification_report(y_test, y_pred))