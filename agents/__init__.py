"""agents 子包：七个角色（hypothesis / bull / bear / risk / redteam / risk_officer / reviewer）。

各角色随 Step 3-6 交付；统一继承 core.base.BaseAgent。
Step 5 新增 redteam（红队审计）与 risk_officer（风控综合官）两个独立角色。
"""

__version__ = "0.2.0"
