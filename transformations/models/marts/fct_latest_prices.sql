with staging as (
    select * from {{ ref('stg_crypto_prices') }}
),

ranked_prices as (
    select
        ticker,
        asset_name,
        price_usd,
        market_cap_usd,
        volume_24h_usd,
        pct_change_24h,
        price_timestamp,
        row_number() over (
            partition by ticker
            order by price_timestamp desc
        ) as dedupe_rank
    from staging
)

select
    ticker,
    asset_name,
    price_usd,
    market_cap_usd,
    volume_24h_usd,
    pct_change_24h,
    price_timestamp
from ranked_prices
where dedupe_rank = 1
