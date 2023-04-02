"""


Пришел пакет

IP не в белом списке - DROP
Белый список - список подключенных клиентов

<action start>
if пакет == qconnect:
    bpf_tail_call(prog_array, qconnect_prog_index);
    return TC_ACT_SHOT;  // сюда никогда не дойдем
<action end>

<action start>
if пакет == A2S:
    bpf_tail_call(prog_array, a2s_prog_index);
    return TC_ACT_SHOT;  // сюда никогда не дойдем
<action end>


return TC_ACT_SHOT; // по умолчанию отбрасываем пакет

----

- У каждого сервереа (порта) своя программа защиты
    - Защищаемые порты храним в BPF_HASH: port -> prog_index
    - Далее BPF_PROG_ARRAY: prog_index -> prog_fd (bpf_tail_call)

- Т

- qconnect - добавляем в белый список
- a2s (not whitelist) - ratelimit (IP ratelimit exceed - ban)
- a2s (whitelist) - pass
"""
