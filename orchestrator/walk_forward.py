"""
orchestrator/walk_forward.py
───────────────────────────
Walk-Forward Validation Engine for NSE Strategies.
Implements expanding window temporal splits.
"""

from orchestrator.vibe_logger import exhaustive_log
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import List, Tuple
import sys
from pathlib import Path

# Add india-trade-cli to path if not present
project_root = Path(__file__).parent.parent
india_trade_cli_path = str(project_root / "india-trade-cli")
if india_trade_cli_path not in sys.path:
    sys.path.insert(0, india_trade_cli_path)

from agent.ensemble_agent import EnsembleTrader

class WalkForwardValidator:
    """
    Simulates training and testing over expanding temporal windows.
    """

    @exhaustive_log
    def __init__(self, initial_train_days: int = 365, test_days: int = 30):
        self.initial_train_days = initial_train_days
        self.test_days = test_days
        self.trader = EnsembleTrader()

    @exhaustive_log
    def split_data(self, df: pd.DataFrame) -> List[Tuple[pd.DataFrame, pd.DataFrame]]:
        """
        Creates expanding window splits.
        """
        splits = []
        df = df.sort_index()
        
        # Start index for testing
        start_date = df.index[0] + pd.Timedelta(days=self.initial_train_days)
        
        current_test_start = start_date
        while current_test_start < df.index[-1]:
            train_data = df[df.index < current_test_start]
            test_end = current_test_start + pd.Timedelta(days=self.test_days)
            test_data = df[(df.index >= current_test_start) & (df.index < test_end)]
            
            if not test_data.empty:
                splits.append((train_data, test_data))
            
            current_test_start = test_end
            
        return splits

    @exhaustive_log
    def run_validation(self, df: pd.DataFrame, target_col='Target'):
        """
        Execute the walk-forward cycle.
        """
        results = []
        splits = self.split_data(df)
        print(f"Starting Walk-Forward Validation with {len(splits)} splits...")

        for i, (train, test) in enumerate(splits):
            print(f"Processing Split {i+1}/{len(splits)} | Train size: {len(train)} | Test size: {len(test)}")
            
            # Prepare data
            train_proc = self.trader.engineer_features(train)
            test_proc = self.trader.engineer_features(test)
            
            if train_proc.empty or test_proc.empty:
                continue

            X_train, y_train = self.trader.prepare_data(train_proc, target_col)
            X_test, y_test = self.trader.prepare_data(test_proc, target_col)

            # Train
            self.trader.train(X_train, y_train)

            # Validate
            score = self.trader.model.score(X_test, y_test)
            results.append(score)
            print(f"Split {i+1} Accuracy: {score:.4f}")

        avg_acc = np.mean(results) if results else 0
        print(f"Validation Complete. Average Accuracy: {avg_acc:.4f}")
        return avg_acc

if __name__ == "__main__":
    # Mock usage / Testing
    data = {
        'Open': np.random.randn(2000) + 100,
        'High': np.random.randn(2000) + 102,
        'Low': np.random.randn(2000) + 98,
        'Close': np.random.randn(2000) + 100,
        'Volume': np.random.randint(1000, 10000, 2000),
        'Target': np.random.choice([0, 1, -1], 2000)
    }
    dates = pd.date_range(start='2020-01-01', periods=2000, freq='D')
    df = pd.DataFrame(data, index=dates)
    
    validator = WalkForwardValidator(initial_train_days=730, test_days=90)
    validator.run_validation(df)
