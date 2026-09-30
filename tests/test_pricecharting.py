from __future__ import annotations

from scrapertc.cards.collectors import _parse_pricecharting, _pokemontcg_query

SAMPLE = """
<tr id="product-715593" data-product="715593">
  <td class="image">
    <a href="https://www.pricecharting.com/game/pokemon-base-set/charizard-1st-edition-4">
      <img class="photo"
           src="https://storage.googleapis.com/images.pricecharting.com/abc/60.jpg" />
    </a>
  </td>
  <td class="title">
    <a href="https://www.pricecharting.com/game/pokemon-base-set/charizard-1st-edition-4">
      Charizard [1st Edition] #4</a>
    <div class="console-in-title">
      <a href="/console/pokemon-base-set">Pokemon Base Set</a>
    </div>
  </td>
  <td class="price numeric used_price">
    <span class="js-price">$9,541.19</span>
  </td>
</tr>
"""


def test_parse_pricecharting_live_row():
    items = _parse_pricecharting(SAMPLE, query="Charizard Base", limit=5)
    assert len(items) == 1
    item = items[0]
    assert item.source == "pricecharting"
    assert "charizard-1st-edition-4" in item.url
    assert item.price_usd == 9541.19
    assert item.extra.get("live") is True
    assert item.image_urls


def test_pokemontcg_query_prefers_original_base_set():
    q = _pokemontcg_query("Charizard Base Set 4/102")
    assert 'name:"Charizard"' in q
    assert 'set.name:"Base"' in q
    assert "number:4" in q
