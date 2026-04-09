# Midas Autonomous Investment Assistant

1. Objective
- I don't want to monitor it
- It should make the best investment decisions
- Make me money

2. Risks
- Turbulent markets, high risks situation, don't trade without asking for my permission
- In normal markets, go ahead

3. Markets and instruments
- We only have access to brokers like IBKR, Interactive Brokers
- We can trade stocks and ETFs

4. Strategies
- Portfolio 
    - ETFs for diversification and sector rotation
    - Precious Metals
    - Bonds
        - Government bonds (all durations to consider)
        - Corporate high quality
    - REITs
    - Commodities
    - Dividend funds
    - Emerging markets
- There is no free lunch
    - There is no 1 instrucment that is always best
    - Agile rotation is important 
- Risk Profile
    - Go big or go home!
    - Its one thing to be risk-loving, its another thing to be reckless and stupid. Don't be the latter 
- Rebalancing
    - Depends on the market regime
    - Never more than once a week

5. Constraints
- Concerned about transaction fees, which can be contributed by over-trading etc.

6. Risk management
- backtest comprehensively across all market conditions
- Do not just use 1 set of horizon but multiple sub horizons to ensure that your strategies are consistent

7. Metrics
- Apply accurate algorithms for transaction costs
    - fees, price impact, slippage
    - gap up, gap down
- Apply fees
    - Commissions, exchange, regulatory

8. UI/UX
- Web, iOS, Android interface
- Well-designed with modern UI UX features that allows rapid decision making to execution
- I need to debate with the AI as and when I require
- Consider commercializing it as a product

9. Data Sources
- yahoo finance as backup
- eodhd api key in .env
- Always use a fabric instead of pulling data all the time, store whatever you have collected and re-use
- Setup a common database for all users
- Data latency is critical so do aggressive caching
- Real time data is not necessary, but activate polling when screen is active.
- news is important, use perplexity api key in .env (fill in later)