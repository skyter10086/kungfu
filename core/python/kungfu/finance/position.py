
from kungfu.wingchun.constants import *
from kungfu.wingchun.utils import *

class Position:
    def __init__(self, **kwargs):
        self._instrument_id = kwargs.pop("instrument_id")
        self._exchange_id = kwargs.pop("exchange_id")
        self._instrument_type = kwargs.pop("instrument_type", get_instrument_type(instrument_id, exchange_id))
        self._symbol_id = get_symbol_id(self._instrument_id, self._exchange_id)

        self._last_price = kwargs.pop("last_price", 0.0)

        self._ledger = kwargs.pop("ledger", None)

    @property
    def instrument_type(self):
        return self._instrument_type

    @property
    def instrument_id(self):
        return self._instrument_id

    @property
    def exchange_id(self):
        return self._exchange_id

    @property
    def symbol_id(self):
        return self._symbol_id

    @property
    def margin(self):
        raise NotImplementationError

    @property
    def market_value(self):
        raise NotImplementationError

    @property
    def last_price(self):
        return self._last_price

    @property
    def realized_pnl(self):
        raise NotImplementationError

    @@property
    def unrealized_pnl(self):
        raise NotImplementationError

    @property
    def ledger(self):
        return self._ledger

    @ledger.setter
    def ledger(self, value):
        self._ledger = value

    def apply_trade(self, trade):
        raise NotImplementationError

    def apply_quote(self, quote):
        raise NotImplementationError

    def apply_settlement(self, close_price):
        raise NotImplementationError

    def switch_day(self, trading_day):
        raise NotImplementationError

class StockPosition(Position):
    def __init__(self, **kwargs):
        super(StockPosition, self).__init__(**kwargs)
        self._volume = kwargs.pop("volume", 0)
        self._yesterday_volume = kwargs.pop("yesterday_volume", 0)

        self._avg_open_price = kwargs.pop("open_price", 0.0)
        if self._avg_open_price <= 0.0:
            self._avg_open_price = kwargs.pop("cost_price", 0.0) # fill with position cost price
        self._close_price = kwargs.pop("close_price", 0.0)
        self._pre_close_price = kwargs.pop("pre_close_price", 0.0)

        self._realized_pnl = kwargs.pop("realized_pnl", 0.0)

    @property
    def volume(self):
        return self._volume

    @property
    def yesterday_volume(self):
        return self._yesterday_volume

    @property
    def close_price(self):
        return self._close_price

    @property
    def pre_close_price(self):
        return self._pre_close_price

    @property
    def market_value(self):
        return self.volume * (self.last_price if self.last_price > 0.0 else self.avg_open_price)

    @property
    def avg_open_price(self):
        return self._avg_open_price

    @property
    def realized_pnl(self):
        return self._realized_pnl

    @property
    def unrealized_pnl(self):
        return (self.last_price - self.avg_open_price) * self.volume if self.last_price > 0.0 else 0.0

    def apply_trade(self, trade):
        if trade.side == Side.Buy:
            return self._apply_buy(trade.price, trade.volume)
        else:
            return self._apply_sell(trade.price, trade.volume)

    def apply_settlement(self, close_price):
        self.close_price = close_price

    def switch_day(self, trading_day):
        self.pre_close_price = self.close_price
        self.close_price = 0.0

    def _apply_sell(self, price, volume):
        realized_pnl = self._calculate_realized_pnl(price, volume)
        self._realized_pnl += realized_pnl
        self.ledger.realized_pnl += realized_pnl
        self.ledger.avail += (realized_pnl + price * volume)

    def _apply_buy(self, price, volume):
        self.avg_open_price = (self.avg_open_price * self.volume + price * volume) / (self.volume + volume)
        self.volume += volume
        self.ledger.avail -= price * volume

    def _calculate_realized_pnl(self, trade_price, trade_volume):
        return (trade_price - self.avg_open_price) * trade_volume

class FuturePositionDetail:
    def __init__(self, **kwargs):
        self._open_price = kwargs.pop("open_price")
        self._open_date = kwargs.pop("open_date")
        self._trading_day = kwargs.pop("trading_day")
        self._direction = kwargs.pop("direction")
        self._volume = kwargs.pop("volume")
        self._contract_multiplier = kwargs.pop("contract_multiplier")
        self._margin_ratio = kwargs.pop("margin_ratio")
        self._settlement_price = kwargs.pop("settlement_price", 0.0)
        self._pre_settlement_price = kwargs.pop("pre_settlement_price", 0.0)

    @property
    def open_date(self):
        return self._open_date

    @property
    def open_price(self):
        return self._open_price

    @property
    def trading_day(self):
        return self._trading_day

    @property
    def margin(self):
        price = self.settlement_price if self.trading_day == self.open_date else self.pre_settlement_price
        if price <= 0.0:
            price = self.open_price
        return self._calculate_margin(price, self.volume)

    @property
    def volume(self):
        return self._volume

    @property
    def pre_settlement_price(self):
        return self._pre_settlement_price

    @property
    def settlement_price(self):
        return self._settlement_price

    @property
    def open_price(self):
        return self._open_price

    def apply_close(self, price, volume):
        volume_closed = min(self.volume, volume)
        realized_pnl = self._calculate_realized_pnl(price, volume_closed)
        margin_delta = self._calculate_margin(price, volume_closed) * -1
        return (volume_closed, realized_pnl, margin_delta)

    def apply_settlement(self, settlement_price):
        pre_margin = self.margin
        self.settlement_price = settlement_price
        return self.pre_margin - self.margin

    def _calculate_realized_pnl(self, trade_price, trade_volume):
        return (trade_price - self._open_price) * trade_volume * self._contract_multiplier * (1 if self._direction == DirectionLong else -1)

    def _calculate_margin(self, price, volume):
        return self._contract_multiplier * price * volume * self._margin_ratio

class FuturePosition(Position):
    def __init__(self, **kwargs):
        super(FuturePosition, self).__init__(**kwargs)
        self._long_details = []
        self._short_details = []

    @property
    def realized_pnl(self):
        return self._realized_pnl

    @property
    def margin(self):
        return self.long_margin + self.short_margin

    @property
    def long_margin(self):
        return [detail.margin for detail in self._long_details]

    @property
    def short_margin(self):
        return [detail.margin for detail in self._short_details]

    def apply_close(self, trade):
        details = self._long_details #TODO choose long or short
        volume_left = trade.volume
        while volume_left > 0 and not details.empty():
            detail = details[0]
            volume_closed, realized_pnl, margin_delta = detail.apply_close(trade.price, volume_left)
            self.realized_pnl += realized_pnl
            self.ledger.avail += (realized_pnl - margin_delta)
            if detail.volume <= 0:
                details.pop(0)

    def apply_open(self, trade):
        details = self._long_details #TODO choose long or short
        detail = FuturePositionDetail(trading_day="", open_price = trade.price, volume = trade.volume, open_date="")
        self.ledger.avail -= detail.margin
        details.append(detail)

    def apply_settlement(self, settlement_price):
        margin_delta = 0.0
        for detail in [self._long_details + self._short_details]:
            margin_delta += detail.apply_settlement(settlement_price)
        self.ledger.avail -= margin_delta


