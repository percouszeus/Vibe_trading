"""
agent/ensemble_agent.py
───────────────────────
Ensemble Quantitative Agent using Voting Classifier.
Integrates models from manav363 and ShreyashDarade research.
"""

from orchestrator.vibe_logger import exhaustive_log
import pandas as pd
import numpy as np
from sklearn.ensemble import RandomForestClassifier, VotingClassifier, GradientBoostingClassifier
from xgboost import XGBClassifier
from lightgbm import LGBMClassifier
from sklearn.preprocessing import StandardScaler
import joblib
import os
from pathlib import Path

# BUG-17 FIX: Use absolute path consistent with the rest of the system
# to avoid CWD-dependent directory creation at import time
MODEL_DIR = Path.home() / ".trading_platform" / "models" / "ensemble"
MODEL_DIR.mkdir(parents=True, exist_ok=True)

class EnsembleTrader:
    """
    Ensemble model for Indian Stock Market (NSE/BSE).
    Uses a Voting Classifier (Soft Voting) of RF, XGB, LGBM, and GBT.
    """

    @exhaustive_log
    def __init__(self):
        self.scaler = StandardScaler()
        self.model = None
        self._is_trained = False

    @exhaustive_log
    def build_ensemble(self):
        """Initialize the ensemble with default hyperparameters."""
        rf = RandomForestClassifier(n_estimators=200, max_depth=10, random_state=42)
        xgb = XGBClassifier(n_estimators=200, learning_rate=0.05, max_depth=6, use_label_encoder=False, eval_metric='logloss')
        lgbm = LGBMClassifier(n_estimators=200, learning_rate=0.05, max_depth=6, num_leaves=31)
        gbt = GradientBoostingClassifier(n_estimators=200, learning_rate=0.05, max_depth=5)

        self.model = VotingClassifier(
            estimators=[
                ('rf', rf),
                ('xgb', xgb),
                ('lgbm', lgbm),
                ('gbt', gbt)
            ],
            voting='soft'
        )

    @exhaustive_log
    def engineer_features(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Calculates technical indicators as features.
        Enhanced with Bollinger Bands, Williams %R, and MFI.
        """
        df = df.copy()
        
        # Returns
        df['ret_1'] = df['Close'].pct_change(1)
        df['ret_5'] = df['Close'].pct_change(5)
        df['ret_20'] = df['Close'].pct_change(20)

        # Volatility
        df['volatility_20'] = df['ret_1'].rolling(window=20).std() * np.sqrt(252)

        # RSI
        delta = df['Close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        rs = gain / loss
        df['rsi'] = 100 - (100 / (1 + rs))

        # MACD
        exp1 = df['Close'].ewm(span=12, adjust=False).mean()
        exp2 = df['Close'].ewm(span=26, adjust=False).mean()
        df['macd'] = exp1 - exp2
        df['macd_signal'] = df['macd'].ewm(span=9, adjust=False).mean()
        df['macd_hist'] = df['macd'] - df['macd_signal']

        # ATR
        high_low = df['High'] - df['Low']
        high_close = np.abs(df['High'] - df['Close'].shift())
        low_close = np.abs(df['Low'] - df['Close'].shift())
        ranges = pd.concat([high_low, high_close, low_close], axis=1)
        true_range = np.max(ranges, axis=1)
        df['atr'] = true_range.rolling(14).mean()

        # Bollinger Bands
        df['sma_20'] = df['Close'].rolling(window=20).mean()
        df['std_20'] = df['Close'].rolling(window=20).std()
        df['bb_upper'] = df['sma_20'] + (df['std_20'] * 2)
        df['bb_lower'] = df['sma_20'] - (df['std_20'] * 2)
        df['bb_pct'] = (df['Close'] - df['bb_lower']) / (df['bb_upper'] - df['bb_lower'])

        # Williams %R
        high_14 = df['High'].rolling(window=14).max()
        low_14 = df['Low'].rolling(window=14).min()
        df['williams_r'] = -100 * (high_14 - df['Close']) / (high_14 - low_14)

        # Money Flow Index (MFI)
        typical_price = (df['High'] + df['Low'] + df['Close']) / 3
        money_flow = typical_price * df['Volume']
        positive_flow = pd.Series(0.0, index=df.index)
        negative_flow = pd.Series(0.0, index=df.index)
        positive_flow.loc[typical_price > typical_price.shift(1)] = money_flow
        negative_flow.loc[typical_price < typical_price.shift(1)] = money_flow
        mfi_ratio = positive_flow.rolling(window=14).sum() / negative_flow.rolling(window=14).sum()
        df['mfi'] = 100 - (100 / (1 + mfi_ratio))

        # Volume
        df['vol_sma_20'] = df['Volume'].rolling(window=20).mean()
        df['vol_ratio'] = df['Volume'] / df['vol_sma_20']

        return df.dropna()

    @exhaustive_log
    def prepare_data(self, df: pd.DataFrame, target_col='Target'):
        """Split features and target, scale features."""
        # Drop non-feature columns if they exist
        drop_cols = [target_col, 'Open', 'High', 'Low', 'Close', 'Volume']
        X = df.drop(columns=[c for c in drop_cols if c in df.columns])
        y = df[target_col] if target_col in df.columns else None
        
        # Scale features
        if self._is_trained:
            X_scaled = self.scaler.transform(X)
        else:
            X_scaled = self.scaler.fit_transform(X)
            
        return X_scaled, y

    @exhaustive_log
    def train(self, X, y):
        """Train the ensemble model."""
        if self.model is None:
            self.build_ensemble()
        self.model.fit(X, y)
        self._is_trained = True

    @exhaustive_log
    def predict(self, df: pd.DataFrame):
        """
        Generate prediction and confidence.
        Target: 1 (Buy), 0 (Hold/None), -1 (Sell)
        """
        if not self._is_trained:
            raise ValueError("Model not trained.")

        features = self.engineer_features(df).tail(1)
        if features.empty:
            return 0, 0.0

        # BUG-03 FIX: Drop raw OHLCV columns before transform — the scaler
        # was fit on data with these columns already removed by prepare_data().
        drop_cols = ['Open', 'High', 'Low', 'Close', 'Volume', 'Target']
        features = features.drop(columns=[c for c in drop_cols if c in features.columns])

        X = self.scaler.transform(features)
        prob = self.model.predict_proba(X)[0]
        pred = self.model.predict(X)[0]
        confidence = prob[np.argmax(prob)]

        return pred, confidence

    @exhaustive_log
    def save(self, name="vibe_ensemble.joblib"):
        """Persist model and scaler."""
        joblib.dump({'model': self.model, 'scaler': self.scaler}, MODEL_DIR / name)

    @exhaustive_log
    def load(self, name="vibe_ensemble.joblib"):
        """Load persisted model and scaler."""
        model_path = MODEL_DIR / name
        if not model_path.exists():
            return False
            
        data = joblib.load(model_path)
        self.model = data['model']
        self.scaler = data['scaler']
        self._is_trained = True
        return True

    @exhaustive_log
    def analyze(self, symbol: str, days: int = 500) -> dict:
        """
        End-to-end analysis method.
        Downloads data, trains if necessary, and predicts.
        """
        from market.history import get_historical_data
        
        # Load data
        df = get_historical_data(symbol, str(days) + 'd', '1d')
        if df.empty or len(df) < 50:
            return {"verdict": "UNKNOWN", "score": 0, "confidence": 0, "error": "Insufficient data"}
            
        # For a full implementation, we'd load a pre-trained model.
        # If it doesn't exist, we fallback to a neutral prediction or simple heuristic,
        # or we train on the fly (which is slow but possible).
        if not self._is_trained:
            loaded = self.load()
            if not loaded:
                # Mock training for real-time capability if no model exists
                # In production, models should be pre-trained.
                # Generate a dummy target for on-the-fly training
                df_train = df.copy()
                df_train['Target'] = np.where(df_train['Close'].shift(-1) > df_train['Close'], 1, -1)
                train_proc = self.engineer_features(df_train)
                if len(train_proc) > 10:
                    X_train, y_train = self.prepare_data(train_proc, 'Target')
                    self.train(X_train, y_train)
                    self.save()
        
        try:
            pred, confidence = self.predict(df)
            
            # Map prediction to verdict
            if pred == 1:
                verdict = "BULLISH"
                score = int(confidence * 100) if confidence > 0.5 else 50
            elif pred == -1:
                verdict = "BEARISH"
                score = -int(confidence * 100) if confidence > 0.5 else -50
            else:
                verdict = "NEUTRAL"
                score = 0
                
            return {
                "verdict": verdict,
                "score": score,
                "confidence": int(confidence * 100),
                "probability": float(confidence),
                "top_features": ["rsi", "macd", "volatility_20"] # Mock top features
            }
        except Exception as e:
            return {"verdict": "UNKNOWN", "score": 0, "confidence": 0, "error": str(e)}
