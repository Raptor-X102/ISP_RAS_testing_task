# Отчет по исправлению утечки памяти в подсистеме XFRM ядра Linux

## Введение
Данный отчет описывает процесс исследования и исправления утечки памяти в подсистеме XFRM ядра Linux версии 6.18. Утечка была обнаружена инструментом фаззинг-тестирования syzkaller.

**Исходная проблема:** `BUG: memory leak` — unreferenced object размера 1024 байта, связанный с `xfrm_policy_alloc`.

**Корневая причина:** Некорректное управление счётчиком ссылок (`refcount_t`) для структур `xfrm_policy`, в частности:
- Двойной вызов `xfrm_pol_hold_rcu()` без парного `xfrm_pol_put()`.

## 1. Подготовка окружения

### 1.1 Установка зависимостей (Manjaro Linux)
```bash
sudo pacman -Syu
sudo pacman -S make gcc flex bison ncurses elfutils openssl
sudo pacman -S debootstrap
sudo pacman -S qemu-system-x86
```

### 1.2 Клонирование репозитория ядра
```bash
git clone https://git.kernel.org/pub/scm/linux/kernel/git/torvalds/linux.git
cd linux
git checkout v6.18
```

### 1.3 Настройка конфигурации ядра
```
# Копирование предоставленного конфига
cp ../kernel-config .config

# Включение опций для отладки (GDB)
./scripts/config -e GDB_SCRIPTS -e KGDB -e KGDB_KDB

# Регенерация конфигурации
make olddefconfig
```

### 1.4 Сборка ядра
```bash
make -j$(nproc)
```
После сборки образ ядра будет доступен по пути: `./arch/x86/boot/bzImage`

### 1.5 Создание образа диска для виртуальной машины
```bash
mkdir kernel-image && cd kernel-image
wget https://raw.githubusercontent.com/google/syzkaller/master/tools/create-image.sh
chmod +x create-image.sh
./create-image.sh --distribution bullseye
```
Образ диска будет создан как `bullseye.img`.

### 1.6 Запуск виртуальной машины
Запуск QEMU с образом ядра и диска. **Важно:** Флаг `-s` откроет порт 1234 для подключения отладчика GDB (`-gdb tcp::1234`). Это позволяет подключиться к работающему ядру извне для пошаговой отладки.

```bash
qemu-system-x86_64 \
  -m 4G \
  -smp 8 \
  -kernel linux/arch/x86/boot/bzImage \
  -append "nokaslr console=ttyS0 root=/dev/sda earlyprintk=serial net.ifnames=0 panic_on_warn=1" \
  -drive file=linux/kernel-image/bullseye.img,format=raw \
  -net user,host=10.0.2.10,hostfwd=tcp:127.0.0.1:10021-:22 \
  -net nic,model=e1000 \
  -monitor telnet:127.0.0.1:55555,server,nowait \
  -enable-kvm \
  -nographic \
  -s \
  -pidfile vm.pid \
  2>&1 | tee vm.log
```

### 1.7 Подключение и перенос файлов

Подключение по SSH внутри гостевой ОС:
```bash
ssh -i linux/kernel-image/bullseye.id_rsa -p 10021 -o "StrictHostKeyChecking=no" root@localhost
```

Перенос репродьюсера на виртуальную машину:
```bash
scp -i linux/kernel-image/bullseye.id_rsa -P 10021 -o "StrictHostKeyChecking=no" ../repro.c root@localhost:
```
Виртуальная машина готова к работе. Дальнейшие шаги посвящены поиску и исправлению ошибки.

## 2. Анализ проблемы

### 2.1 Исходный отчёт об ошибке (CrashReport)

<details>
<summary>Развернуть полный вывод CrashReport</summary>

```
2026/03/12 21:10:03 executed programs: 2
BUG: memory leak
unreferenced object 0xffff888114d79000 (size 1024):
  comm "syz.1.17", pid 931, jiffies 4294763714
  hex dump (first 32 bytes):
    c0 18 52 07 81 88 ff ff 00 00 00 00 00 00 00 00  ..R.............
    22 01 00 00 00 00 ad de 00 01 00 00 00 00 ad de  "...............
  backtrace (crc ec61b4b7):
    create_object mm/kmemleak.c:794 [inline]
    kmemleak_alloc+0x39/0x70 mm/kmemleak.c:1098
    kmemleak_alloc_recursive include/linux/kmemleak.h:44 [inline]
    slab_post_alloc_hook mm/slub.c:4983 [inline]
    slab_alloc_node mm/slub.c:5288 [inline]
    __kmalloc_cache_noprof+0x56b/0xc40 mm/slub.c:5766
    kmalloc_noprof include/linux/slab.h:957 [inline]
    kzalloc_noprof include/linux/slab.h:1094 [inline]
    xfrm_policy_alloc+0xb3/0x4b0 net/xfrm/xfrm_policy.c:432
    xfrm_policy_construct+0x3b/0x510 net/xfrm/xfrm_user.c:2187
    xfrm_add_policy+0x470/0xa20 net/xfrm/xfrm_user.c:2246
    xfrm_user_rcv_msg+0x46d/0xe30 net/xfrm/xfrm_user.c:3507
    netlink_rcv_skb+0x17f/0x510 net/netlink/af_netlink.c:2552
    xfrm_netlink_rcv+0x8c/0xc0 net/xfrm/xfrm_user.c:3529
    netlink_unicast_kernel net/netlink/af_netlink.c:1320 [inline]
    netlink_unicast+0x776/0xcb0 net/netlink/af_netlink.c:1346
    netlink_sendmsg+0xacf/0x1140 net/netlink/af_netlink.c:1896
    sock_sendmsg_nosec+0x1fe/0x250 net/socket.c:727
    __sock_sendmsg+0x89/0xb0 net/socket.c:742
    ____sys_sendmsg+0x6fd/0x9e0 net/socket.c:2630
    ___sys_sendmsg+0x140/0x200 net/socket.c:2684
    __sys_sendmsg+0x180/0x2c0 net/socket.c:2716
    __do_sys_sendmsg net/socket.c:2721 [inline]
    __se_sys_sendmsg net/socket.c:2719 [inline]
    __x64_sys_sendmsg+0x7f/0xc0 net/socket.c:2719
```

</details>

**Ключевой вывод из backtrace:**
```
xfrm_policy_alloc+0xb3/0x4b0 net/xfrm/xfrm_policy.c:432
xfrm_policy_construct+0x3b/0x510 net/xfrm/xfrm_user.c:2187
xfrm_add_policy+0x470/0xa20 net/xfrm/xfrm_user.c:2246
```

Утечка происходит при выделении памяти для `xfrm_policy`, которая не освобождается корректно.

### 2.2 Исследование функций освобождения памяти

Для понимания жизненного цикла `xfrm_policy` были изучены функции, отвечающие за освобождение:

<details>
<summary>xfrm_policy_delete</summary>

```c
int xfrm_policy_delete(struct xfrm_policy *pol, int dir)
{
        struct net *net = xp_net(pol);

        spin_lock_bh(&net->xfrm.xfrm_policy_lock);
        pol = __xfrm_policy_unlink(pol, dir);
        spin_unlock_bh(&net->xfrm.xfrm_policy_lock);
        if (pol) {
                xfrm_policy_kill(pol);
                return 0;
        }
        return -ENOENT;
}
```

</details>

<details>
<summary>xfrm_policy_kill</summary>

```c
static void xfrm_policy_kill(struct xfrm_policy *policy)
{
        struct net *net = xp_net(policy);
        struct xfrm_state *x;

        xfrm_dev_policy_delete(policy);

        write_lock_bh(&policy->lock);
        policy->walk.dead = 1;
        write_unlock_bh(&policy->lock);

        atomic_inc(&policy->genid);

        if (timer_delete(&policy->polq.hold_timer))
                xfrm_pol_put(policy);
        skb_queue_purge(&policy->polq.hold_queue);

        if (timer_delete(&policy->timer))
                xfrm_pol_put(policy);

        /* XXX: Flush state cache */
        spin_lock_bh(&net->xfrm.xfrm_state_lock);
        hlist_for_each_entry_rcu(x, &policy->state_cache_list, state_cache) {
                hlist_del_init_rcu(&x->state_cache);
        }
        spin_unlock_bh(&net->xfrm.xfrm_state_lock);

        xfrm_pol_put(policy);
}
```

</details>

**Наблюдение:** Последнее действие в цепочке освобождения — вызов `xfrm_pol_put(policy)`.

### 2.3 Анализ reference counting

Были изучены функции управления счётчиком ссылок:

```c
// include/net/xfrm.h
static inline void xfrm_pol_hold(struct xfrm_policy *policy)
{
        if (likely(policy != NULL))
                refcount_inc(&policy->refcnt);
}

static inline void xfrm_pol_put(struct xfrm_policy *policy)
{
        if (refcount_dec_and_test(&policy->refcnt))
                xfrm_policy_destroy(policy);
}
```

Функция `xfrm_policy_destroy` использует механизм RCU для отложенного освобождения:

<details>
<summary>xfrm_policy_destroy</summary>

```c
/* Destroy xfrm_policy: descendant resources must be released to this moment. */
void xfrm_policy_destroy(struct xfrm_policy *policy)
{
        BUG_ON(!policy->walk.dead);

        if (timer_delete(&policy->timer) || timer_delete(&policy->polq.hold_timer))
                BUG();

        xfrm_dev_policy_free(policy);
        call_rcu(&policy->rcu, xfrm_policy_destroy_rcu);
}
```

</details>

Реальное освобождение памяти (`kfree`) происходит в коллбэке `xfrm_policy_destroy_rcu`, который вызывается асинхронно после завершения всех RCU-читателей.

<details>
<summary>xfrm_policy_destroy_rcu</summary>

```c
static void xfrm_policy_destroy_rcu(struct rcu_head *head)
{
	struct xfrm_policy *policy = container_of(head, struct xfrm_policy, rcu);

	security_xfrm_policy_free(policy->security);
	kfree(policy);
}
```

</details>

### 2.4 Инструментальная отладка с printk

Для трассировки изменений `refcnt` были добавлены логи в функции `xfrm_pol_hold`, `xfrm_pol_put` и `xfrm_add_policy`.

**Результаты логов** (`dmesg | grep -E "xfrm_add_policy|xfrm_pol_put|xfrm_pol_hold"`):
```
[  167.620706] xfrm_pol_hold: policy=ffff88802246b000 refcnt=2
[  167.628700] xfrm_pol_hold: policy=ffff88802246b000 refcnt=3
[  167.629553] xfrm_add_policy: policy=ffff88802246b000 refcnt=3 (before)
[  167.635658] xfrm_pol_put: policy=ffff88802246b000 refcnt=2
[  167.635701] xfrm_add_policy: policy=ffff88802246b000 refcnt=2 (after)
[  167.641272] xfrm_pol_put: policy=ffff88802246b000 refcnt=3  <-- refcnt УВЕЛИЧИЛСЯ!
[  168.650381] xfrm_pol_put: policy=ffff88802246b000 refcnt=2
[  168.656344] xfrm_pol_put: policy=ffff88802246b000 refcnt=1
```

**Наблюдение:** В строке `[167.641272]` refcnt увеличивается с 2 до 3 без соответствующего вызова `xfrm_pol_hold` в логах. Это указывает на прямой вызов `refcount_inc` или `xfrm_pol_hold_rcu` в обход логирования.

### 2.5 Отладка в GDB: поиск источника лишнего hold

Для точного определения места изменения `refcnt` использовался hardware watchpoint:

```gdb
(gdb) watch -l ((struct xfrm_policy *)0xffff88802246b000)->refcnt
(gdb) continue
```

При срабатывании watchpoint выполнялся backtrace, который показал:

```
#6  xfrm_pol_hold_rcu (policy=0xffff8881146d3000) at net/xfrm/xfrm_policy.c:213
#7  xfrm_policy_lookup_bytype (...) at net/xfrm/xfrm_policy.c:2216
#8  xfrm_migrate_policy_find (...) at net/xfrm/xfrm_policy.c:4517
#9  xfrm_migrate (...) at net/xfrm/xfrm_policy.c:4663
#10 xfrm_do_migrate (...) at net/xfrm/xfrm_user.c:3156
```

**Ключевое открытие:** Функция `xfrm_pol_hold_rcu` (отличная от `xfrm_pol_hold`) увеличивает refcount в RCU-контексте, но не всегда сопровождается парным `xfrm_pol_put`.

Для трассировки этой функции был добавлен лог и убран модификатор `inline`:

```c
static bool xfrm_pol_hold_rcu(struct xfrm_policy *policy)
{
        bool result = refcount_inc_not_zero(&policy->refcnt);
        printk(KERN_DEBUG "xfrm_pol_hold_rcu: policy=%p refcnt=%d\n",
                       policy, refcount_read(&policy->refcnt));
        return result;
}
```

### 2.6 Обнаружение корневой причины: двойной xfrm_pol_hold_rcu

Анализ кода показал, что `xfrm_migrate_policy_find` вызывает `xfrm_pol_hold_rcu` дважды:

1. **Первый вызов** — внутри `xfrm_policy_lookup_bytype` (строка 2216):
```c
// xfrm_policy_lookup_bytype
if (ret && !xfrm_pol_hold_rcu(ret))
        goto retry;
// Возвращает policy с уже увеличенным refcount
```

2. **Второй вызов** — в `xfrm_migrate_policy_find` (строка 4521):
```c
// xfrm_migrate_policy_find
pol = xfrm_policy_lookup_bytype(...);  // Уже с held ссылкой!
if (IS_ERR_OR_NULL(pol))
        goto out_unlock;

if (!xfrm_pol_hold_rcu(pol))  // ДУБЛИРОВАНИЕ!
        pol = NULL;
```

**Результат:**
```
refcnt: 1 -> 2 (в xfrm_policy_lookup_bytype)
refcnt: 2 -> 3 (в xfrm_migrate_policy_find) <-- ЛИШНИЙ!
...
refcnt: 3 -> 2 (xfrm_pol_put в xfrm_migrate)
refcnt: 2 -> НИКОГДА НЕ ОСВОБОЖДАЕТСЯ! <-- УТЕЧКА
```

## 3. Исправление

### 3.1 Устранение дублирующего xfrm_pol_hold_rcu

**Файл:** `net/xfrm/xfrm_policy.c`  
**Функция:** `xfrm_migrate_policy_find`  

**Применённый патч:**
```diff
        if (IS_ERR_OR_NULL(pol))
                goto out_unlock;

-       if (!xfrm_pol_hold_rcu(pol))
-               pol = NULL;
-
 out_unlock:
        rcu_read_unlock();
        return pol;
 }
```

**Обоснование:** `xfrm_policy_lookup_bytype` уже гарантирует, что возвращаемая политика имеет увеличенный `refcount`. Дополнительный вызов `xfrm_pol_hold_rcu` в `xfrm_migrate_policy_find` избыточен и приводит к утечке.

## 4. Верификация исправления

### 4.1 Запуск репродьюсера

```bash
root@syzkaller:~# timeout 60 ./repro
[   97.046615] audit: type=1400 audit(1774811213.178:7): avc:  denied  { execmem } for  pid=877 comm="repro" scontext1
executing program
executing program
executing program
executing program
executing program
root@syzkaller:~#
```

**Наблюдение:** Программа работает в цикле и не завершается с ошибкой, что указывает на отсутствие обнаруженных утечек.

### 4.2 Проверка kmemleak

```bash
root@syzkaller:~# echo scan > /sys/kernel/debug/kmemleak
root@syzkaller:~# cat /sys/kernel/debug/kmemleak
root@syzkaller:~#
```

**Результат:** Вывод пуст — утечки памяти не обнаружены.

## 5. Выводы

1. **Корневая причина утечки:** Двойной вызов `xfrm_pol_hold_rcu()` в функции `xfrm_migrate_policy_find`, приводящий к дисбалансу reference counting.

2. **Методология отладки:**
   - Анализ backtrace из CrashReport для локализации места аллокации
   - Изучение цепочки функций освобождения памяти
   - Инструментальная трассировка через `printk` для мониторинга `refcnt`
   - Использование hardware watchpoint в GDB для точного определения места изменения `refcnt`

3. **Исправление:** Удаление избыточного вызова `xfrm_pol_hold_rcu()` в `xfrm_migrate_policy_find`.

4. **Результат:** Утечка памяти устранена, репродьюсер работает без ошибок, `kmemleak` не фиксирует утечек.

5. **Чему научился в ходе выполнения задания** 1. Собирать ядро и образ. 2. Работать с gdb (очень крутой и полезный инструмент, жаль раньше не использовал).
---

## Приложения

### A. Использованные команды отладки

Для того чтобы не писать каждый раз команды в gdb, использовался загрузочный файл kernel_breakpoints.gdb. Пример содержания

```bash
target remote:1234
set remotetimeout 3600
break xfrm_add_policy
break xfrm_pol_hold_rcu
break xfrm_migrate
break xfrm_pol_put
break xfrm_pol_hold
continue
```

Запуска

```bash
gdb linux/vmlinux -x kernel_breakpoints.gdb
```

Просмотр логов и проверка утечек
```bash
dmesg | grep -E "xfrm_add_policy|xfrm_pol_put|xfrm_pol_hold"

echo scan > /sys/kernel/debug/kmemleak
cat /sys/kernel/debug/kmemleak
```

### B. Список изменённых файлов в ходе исследования

| Файл | Изменение |
|------|-----------|
| `net/xfrm/xfrm_policy.c` | Удалён дублирующий `xfrm_pol_hold_rcu()` в `xfrm_migrate_policy_find`, добавлены отладочные `printk` в `xfrm_pol_hold_rcu` |
| `net/xfrm/xfrm_user.c` | Добавлена отладочная информация в `xfrm_add_policy` |
| `include/net/xfrm.h` | Добавлена отладочная информация в `xfrm_pol_hold`, `xfrm_pol_put` |

