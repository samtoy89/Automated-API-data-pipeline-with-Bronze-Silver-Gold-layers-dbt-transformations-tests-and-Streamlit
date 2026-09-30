with raw_source as (
    select * from {{ source('raw_api', 'raw_crypto_prices') }}
)

select
    upper(symbol) as ticker,
    name as asset_name,
    current_price::double as price_usd,
    market_cap::double as market_cap_usd,
    total_volume::double as volume_24h_usd,
    price_change_percentage_24h::double as pct_change_24h,
    extraction_timestamp::timestamp as price_timestamp
from raw_source
