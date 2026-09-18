import os
import sys
import numpy as np
from sklearn.neural_network import MLPClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler
from sklearn.pipeline import make_pipeline

X = np.random.randn(1000, 20).astype(np.float32)
y_bin = (X[:, 0] + X[:, 1] > 0).astype(np.int32)
y_multi = np.random.randint(0, 4, size=1000)

# Test binary
clf_af = make_pipeline(StandardScaler(), LogisticRegression(class_weight='balanced'))
clf_af.fit(X, y_bin)
p_bin = clf_af.predict(X)
print("Binary LogisticRegression: OK, accuracy=", np.mean(p_bin == y_bin))

# Test multi
clf_bs = make_pipeline(StandardScaler(), LogisticRegression(max_iter=200))
clf_bs.fit(X, y_multi)
p_multi = clf_bs.predict(X)
print("Multiclass LogisticRegression: OK, accuracy=", np.mean(p_multi == y_multi))

# Test MLP
mlp_af = make_pipeline(StandardScaler(), MLPClassifier(hidden_layer_sizes=(64, 32), max_iter=50, random_state=42))
mlp_af.fit(X, y_bin)
print("MLPClassifier: OK")
