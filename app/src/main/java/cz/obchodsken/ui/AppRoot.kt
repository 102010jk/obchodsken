package cz.obchodsken.ui

import android.net.Uri
import androidx.compose.foundation.layout.padding
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.ShoppingCart
import androidx.compose.material3.Icon
import androidx.compose.material3.NavigationBar
import androidx.compose.material3.NavigationBarItem
import androidx.compose.material3.Scaffold
import androidx.compose.material3.SnackbarHost
import androidx.compose.material3.SnackbarHostState
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.remember
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.platform.LocalContext
import androidx.navigation.NavGraph.Companion.findStartDestination
import androidx.navigation.NavHostController
import androidx.navigation.NavType
import androidx.navigation.compose.NavHost
import androidx.navigation.compose.composable
import androidx.navigation.compose.currentBackStackEntryAsState
import androidx.navigation.compose.rememberNavController
import androidx.navigation.navArgument
import cz.obchodsken.App
import cz.obchodsken.data.Repository

private data class Tab(val route: String, val label: String, val icon: ImageVector)

private val tabs = listOf(
    Tab("receipts", "Účtenky", AppIcons.Receipt),
    Tab("scan", "Skenovat", AppIcons.Barcode),
    Tab("products", "Položky", Icons.Default.ShoppingCart),
    Tab("foods", "Potraviny", AppIcons.Food),
    Tab("stats", "Přehled", AppIcons.Chart),
)

@Composable
fun repo(): Repository = (LocalContext.current.applicationContext as App).repo

fun NavHostController.openReceipt(id: Long) = navigate("receipt/$id")
fun NavHostController.openProduct(name: String) = navigate("product/" + Uri.encode(name))

@Composable
fun AppRoot() {
    val nav = rememberNavController()
    val snackbar = remember { SnackbarHostState() }
    val entry by nav.currentBackStackEntryAsState()
    val route = entry?.destination?.route
    Scaffold(
        snackbarHost = { SnackbarHost(snackbar) },
        bottomBar = {
            if (tabs.any { it.route == route }) {
                NavigationBar {
                    tabs.forEach { t ->
                        NavigationBarItem(
                            selected = route == t.route,
                            onClick = {
                                nav.navigate(t.route) {
                                    popUpTo(nav.graph.findStartDestination().id) { saveState = true }
                                    launchSingleTop = true
                                    restoreState = true
                                }
                            },
                            icon = { Icon(t.icon, null) },
                            label = { Text(t.label) },
                        )
                    }
                }
            }
        },
    ) { pad ->
        NavHost(nav, startDestination = "receipts", modifier = Modifier.padding(pad)) {
            composable("receipts") { ReceiptsScreen(nav, snackbar) }
            composable("scan") { ScanScreen(nav) }
            composable("products") { ProductsScreen(nav) }
            composable("foods") { FoodsScreen(nav) }
            composable("stats") { StatsScreen(snackbar) }
            composable("receipt/{id}", arguments = listOf(navArgument("id") { type = NavType.LongType })) {
                ReceiptDetailScreen(it.arguments!!.getLong("id"), nav)
            }
            composable("food/{id}", arguments = listOf(navArgument("id") { type = NavType.LongType })) {
                FoodEditScreen(it.arguments!!.getLong("id"), nav)
            }
            composable("product/{name}") {
                ProductDetailScreen(Uri.decode(it.arguments!!.getString("name")!!), nav)
            }
        }
    }
}
